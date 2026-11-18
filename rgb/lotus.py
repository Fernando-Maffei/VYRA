"""Fitas de LED Bluetooth do aplicativo LotusLamp X (controladoras ELK-BLEDOM, ELK-BLEDOB, MELK...).

Essas controladoras sao BLE e nao passam pelo OpenRGB. Protocolo (o mesmo usado pelos
projetos abertos elkbledom e LotusLantern):

  - servico 0xFFF0, caracteristica de escrita 0xFFF3 (escrita sem resposta);
  - comandos de 9 bytes  7E <tam> <cmd> <p1..p5> EF;
  - cor:    7E 00 05 03 RR GG BB 00 EF   (ELK-BLEDOM)
            7E 07 05 03 RR GG BB 10 EF   (ELK-BLEDOB, MELK e outras do LotusLamp X)
  - ligar:  7E 04 04 F0 00 01 FF 00 EF
  - brilho: 7E 04 01 <0..100> 01 FF FF 00 EF

A fita inteira e de uma cor so (nao e enderecavel): para o VYRA ela e um aparelho de 1 LED.
A controladora aceita uma conexao por vez: com o LotusLamp X aberto no celular ela nem
aparece para o PC.

Precisa da biblioteca bleak (pip install bleak). Sem ela este controle simplesmente nao carrega.
"""
import asyncio, re, threading, time

from . import dispositivos as dsp

ESCRITA = "0000fff3-0000-1000-8000-00805f9b34fb"
NOMES = re.compile(r"^(ELK-|MELK)", re.I)        # como as controladoras do LotusLamp X se anunciam
# A busca fica ligada direto enquanto falta achar ou reconectar alguma fita: em alguns
# adaptadores o Windows passa ~20 s sem receber nada logo depois que uma busca comeca,
# entao buscas curtas e repetidas quase nunca acham a fita.
VISTA_RECENTE = 15.0        # so tenta conectar numa fita anunciada ha pouco
TENTAR_A_CADA = 5.0         # entre tentativas de conexao com a mesma fita
INTERVALO_MIN = 0.03        # no maximo ~33 cores por segundo: mais que isso a controladora engasga
REENVIO = 5.0               # repete a cor parada de vez em quando (e confere que a conexao vive)


def disponivel():
    try:
        import bleak  # noqa: F401
        return True
    except ImportError:
        return False


def _variante(nome):
    return "bledom" if (nome or "").upper().startswith("ELK-BLEDOM") else "bledob"


def cmd_cor(variante, r, g, b):
    if variante == "bledom":
        return bytes((0x7E, 0x00, 0x05, 0x03, r, g, b, 0x00, 0xEF))
    return bytes((0x7E, 0x07, 0x05, 0x03, r, g, b, 0x10, 0xEF))


CMD_LIGAR = bytes((0x7E, 0x04, 0x04, 0xF0, 0x00, 0x01, 0xFF, 0x00, 0xEF))
CMD_BRILHO_MAX = bytes((0x7E, 0x04, 0x01, 100, 0x01, 0xFF, 0xFF, 0x00, 0xEF))


class _Fita:
    def __init__(self, endereco, nome):
        self.endereco, self.nome = endereco, nome
        self.variante = _variante(nome)
        self.cliente = None
        self.aparelho = None        # ultimo anuncio visto (BLEDevice) e quando
        self.vista = 0.0
        self.prox_tentativa = 0.0
        self.cor = None             # pedida pelo motor
        self.enviada = None
        self.quando = 0.0

    @property
    def conectada(self):
        return self.cliente is not None and self.cliente.is_connected


class BackendLotus:
    """Acha, conecta e pinta as fitas, em uma thread propria com o seu laco asyncio."""
    nome = "LotusLamp X"

    def __init__(self):
        self.fitas = {}                 # endereco -> _Fita (vistas alguma vez nesta sessao)
        self.versao = 0                 # sobe quando uma fita aparece, conecta ou cai
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._loop = None
        self._acordar = None
        self._thread = None

    def iniciar(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._rodar, daemon=True, name="lotuslamp-ble")
            self._thread.start()
        return self

    # ---- interface de backend ------------------------------------------------
    def descobrir(self):
        saida = []
        with self._trava:
            fitas = list(self.fitas.values())
        for k, f in enumerate(sorted(fitas, key=lambda f: f.endereco)):
            chave = f"lotus:{f.endereco}"
            nome = f"Fita de LED ({f.nome})"
            if f.conectada:
                saida.append(dsp.Dispositivo(chave=chave, nome=nome, categoria="Outros", estado=dsp.CONECTADO,
                                             fabricante="LotusLamp X", indice=k, zonas=[("Fita", 0, 1)],
                                             limites=[(1, 1)], matrizes=[None], n_leds=1, backend=self))
            else:
                saida.append(dsp.Dispositivo(chave=chave, nome=nome, categoria="Outros", estado=dsp.DESCONECTADO,
                                             fabricante="LotusLamp X", backend=self,
                                             motivo="A fita foi vista pelo Bluetooth, mas a conexão caiu ou não "
                                                    "abriu. Feche o LotusLamp X no celular (a fita só aceita uma "
                                                    "conexão por vez) e confira se ela está ligada na tomada."))
        return saida

    def pintar(self, disp, cores):
        f = self.fitas.get(disp.chave.split(":", 1)[1])
        if not f or not f.conectada or not cores:
            return False
        f.cor = tuple(max(0, min(255, int(v))) for v in cores[0])
        if self._loop and self._acordar:
            self._loop.call_soon_threadsafe(self._acordar.set)
        return True

    def redimensionar(self, disp, tamanhos):
        return False

    def fechar(self):
        self._parar.set()
        if self._loop and self._acordar:
            self._loop.call_soon_threadsafe(self._acordar.set)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(5.0)

    # ---- laco --------------------------------------------------------------------
    def _mudou(self):
        self.versao += 1

    def _rodar(self):
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._principal())
        finally:
            self._loop.close()

    def _anuncio(self, aparelho, adv):
        nome = adv.local_name or aparelho.name or ""
        if not NOMES.match(nome):
            return
        f = self.fitas.get(aparelho.address)
        if f is None:
            with self._trava:
                f = self.fitas[aparelho.address] = _Fita(aparelho.address, nome)
            self._mudou()
        f.aparelho, f.vista = aparelho, time.monotonic()
        self._acordar.set()

    async def _principal(self):
        from bleak import BleakScanner
        self._acordar = asyncio.Event()
        busca = None
        try:
            while not self._parar.is_set():
                faltando = not self.fitas or any(not f.conectada for f in self.fitas.values())
                if faltando and busca is None:
                    try:
                        busca = BleakScanner(self._anuncio)
                        await busca.start()
                    except Exception:           # Bluetooth desligado ou sem adaptador: tenta depois
                        busca = None
                        await asyncio.sleep(5.0)
                elif not faltando and busca is not None:
                    await self._parar_busca(busca)  # com tudo conectado a busca so atrapalharia o radio
                    busca = None
                agora = time.monotonic()
                for f in list(self.fitas.values()):
                    if (not f.conectada and f.aparelho and agora - f.vista < VISTA_RECENTE
                            and agora >= f.prox_tentativa):
                        if busca is not None:   # no Windows, buscar e conectar ao mesmo tempo costuma falhar
                            await self._parar_busca(busca)
                            busca = None
                        await self._conectar(f, f.aparelho)
                        f.prox_tentativa = time.monotonic() + TENTAR_A_CADA
                pendente = await self._enviar()
                self._acordar.clear()
                try:
                    await asyncio.wait_for(self._acordar.wait(), INTERVALO_MIN if pendente else 0.5)
                except asyncio.TimeoutError:
                    pass
        finally:
            if busca is not None:
                await self._parar_busca(busca)
            for f in self.fitas.values():
                if f.cliente:
                    try:
                        await f.cliente.disconnect()
                    except Exception:
                        pass

    @staticmethod
    async def _parar_busca(busca):
        try:
            await busca.stop()
        except Exception:
            pass

    async def _conectar(self, f, aparelho):
        from bleak import BleakClient
        cliente = BleakClient(aparelho, disconnected_callback=lambda _c: self._mudou())
        try:
            await cliente.connect(timeout=20.0)
            await asyncio.sleep(0.5)        # logo apos conectar a controladora ignora o que chega
            await cliente.write_gatt_char(ESCRITA, CMD_LIGAR, response=False)
            await asyncio.sleep(0.2)
            await cliente.write_gatt_char(ESCRITA, CMD_BRILHO_MAX, response=False)
            await asyncio.sleep(0.2)
        except Exception:
            try:
                await cliente.disconnect()
            except Exception:
                pass
            return
        f.cliente, f.enviada = cliente, None
        self._mudou()

    async def _enviar(self):
        """Manda a cor nova de cada fita. Devolve True se alguma ficou esperando o intervalo minimo."""
        agora, pendente = time.monotonic(), False
        for f in list(self.fitas.values()):
            if not f.conectada or f.cor is None:
                continue
            if f.cor == f.enviada and agora - f.quando < REENVIO:
                continue
            if agora - f.quando < INTERVALO_MIN:
                pendente = True
                continue
            cor = f.cor
            try:
                await f.cliente.write_gatt_char(ESCRITA, cmd_cor(f.variante, *cor), response=False)
                f.enviada, f.quando = cor, agora
            except Exception:
                try:
                    await f.cliente.disconnect()
                except Exception:
                    pass
                f.cliente = None
                self._mudou()
        return pendente

