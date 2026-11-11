"""Teclado AULA pelo receptor sem fio 2.4G (USB 3554:FA09), sem passar pelo OpenRGB.

O protocolo segue o que esta documentado no projeto aberto aula-f75-openrgb-wireless
(FallenG101, GPL-2.0), escrito aqui de forma independente:

  - colecao HID da interface 1, pagina 0xFF02, uso 2, report ID 0x13, relatorios de
    20 bytes (byte 19 = soma dos bytes 0..18, modulo 256);
  - consulta de modelo 13 05 01 00 ...: a resposta traz o modelo no byte 10
    (0xCD = AULA F75 Pro, o unico verificado);
  - quadro de cores 13 88 <total> <parte> <0x10 + n> <n bytes de dados>: os dados sao,
    para cada cor distinta, R G B quantidade e os indices das teclas dessa cor,
    divididos em partes de 14 bytes (no maximo 29 partes).

As cores sao transmitidas continuamente e NAO ficam gravadas no teclado: se o
programa parar, o teclado volta ao efeito dele. Por seguranca, nada e enviado para
um modelo que nao responda 0xCD.
"""
import threading, time

from . import dispositivos as dsp, hid

VID, PID = 0x3554, 0xFA09
PAGINA, USO, REPORT_ID = 0xFF02, 0x02, 0x13
DESCRITOR = bytes([0x06, 0x02, 0xFF, 0x09, 0x02, 0xA1, 0x01, 0x85, 0x13, 0x09, 0x02, 0x15, 0x00, 0x26, 0xFF,
                   0x00, 0x75, 0x08, 0x95, 0x13, 0x81, 0x00, 0x09, 0x02, 0x15, 0x00, 0x26, 0xFF, 0x00, 0x75,
                   0x08, 0x95, 0x13, 0x91, 0x00, 0xC0])
MODELOS = {0xCD: "AULA F75 Pro"}
PAUSA_ENVIO = 0.012         # entre um relatorio e o proximo, como no projeto de referencia
RENOVAR = 0.08              # o quadro e reenviado pelo menos a cada 80 ms
SONDAR_A_CADA = 3.0         # enquanto o teclado nao responde
CONFERIR_A_CADA = 30.0      # com o teclado respondendo: confirma que ele continua la
MAX_PARTES = 29

# Indice de cada tecla no teclado, por fileira (de cima para baixo) e a coluna em que ela fica.
_FILEIRAS = [
    ([0, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78], list(range(13))),                    # Esc, F1..F12
    ([1, 7, 13, 19, 25, 31, 37, 43, 49, 55, 61, 67, 73, 79, 85], list(range(15))),             # ` 1..0 - = Bksp Del
    ([2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68, 74, 80, 86], list(range(15))),             # Tab Q..P [ ] \ PgUp
    ([3, 9, 15, 21, 27, 33, 39, 45, 51, 57, 63, 69, 81, 87], list(range(13)) + [14]),          # Caps A..L ; ' Enter PgDn
    ([4, 10, 16, 22, 28, 34, 40, 46, 52, 58, 64, 70, 82, 88], list(range(12)) + [13, 14]),     # Shift Z../ Shift Up End
    ([5, 11, 17, 35, 53, 59, 77, 83, 89], [0, 1, 2, 6, 10, 11, 12, 13, 14]),                   # Ctrl Win Alt Espaco Fn Ctrl < v >
]
HW = [i for idx, _ in _FILEIRAS for i in idx]           # nossa ordem de LED -> indice no teclado
N_LEDS = len(HW)                                         # 80
_VAZIO = 0xFFFFFFFF
MATRIZ = (6, 15, [_VAZIO] * 90)
_k = 0
for _l, (_idx, _cols) in enumerate(_FILEIRAS):
    for _c in _cols:
        MATRIZ[2][_l * 15 + _c] = _k
        _k += 1


def relatorio(corpo):
    """Completa um relatorio de 20 bytes: report ID, corpo, zeros e a soma de verificacao."""
    b = bytearray(20)
    b[0] = REPORT_ID
    b[1:1 + len(corpo)] = corpo
    b[19] = sum(b[:19]) & 0xFF
    return bytes(b)


CONSULTA_MODELO = relatorio(b"\x05\x01\x00")


def _quantizar(cor, passo):
    return tuple(min(255, int(round(v / passo)) * passo) for v in cor) if passo > 1 else tuple(cor)


def _agrupar(cores, passo):
    grupos = {}
    for k, cor in enumerate(cores):
        grupos.setdefault(_quantizar(cor, passo), []).append(HW[k])
    return grupos


def dados_do_quadro(cores):
    """Bytes de dados de um quadro completo (cores na nossa ordem de LED).

    Muitas cores distintas deixam o quadro longo e lento de enviar; por isso as cores
    sao arredondadas o quanto for preciso para caber em ate 10 partes (cerca de 8 quadros
    por segundo), sem nunca passar de 29.
    """
    for passo in (1, 8, 16, 32, 64):
        grupos = _agrupar(cores, passo)
        tamanho = sum(4 + len(v) for v in grupos.values())
        if -(-tamanho // 14) <= 10 or passo == 64:
            break
    dados = bytearray()
    for (r, g, b), indices in grupos.items():
        for i in range(0, len(indices), 255):
            parte = indices[i:i + 255]
            dados += bytes((r, g, b, len(parte))) + bytes(parte)
    return bytes(dados)


def relatorios_do_quadro(cores):
    """Lista de relatorios de 20 bytes que transmitem um quadro."""
    dados = dados_do_quadro(cores)
    partes = [dados[i:i + 14] for i in range(0, len(dados), 14)] or [b""]
    if len(partes) > MAX_PARTES:
        raise ValueError(f"quadro grande demais ({len(partes)} partes)")
    return [relatorio(bytes((0x88, len(partes), k, 0x10 + len(p))) + p) for k, p in enumerate(partes)]


def resposta_de_modelo(r):
    """Byte do modelo, se r for uma resposta valida a consulta; senao None."""
    if len(r) >= 20 and r[:4] == b"\x13\x05\x01\x00" and r[19] == sum(r[:19]) & 0xFF:
        return r[10]
    return None


class BackendAULA:
    """Controla o teclado pelo receptor, em uma thread propria (envio e deteccao)."""
    nome = "AULA 2.4G"

    def __init__(self, transporte=None):
        self.hid = transporte or hid           # trocavel nos testes
        self.estado = "ausente"                 # ausente | sem_resposta | desconhecido | conectado
        self.modelo = None
        self.versao_hw = None
        self.versao = 0                         # sobe a cada mudanca de estado
        self.enviados = 0
        self._h = None
        self._quadro = None
        self._trava = threading.Lock()
        self._novo = threading.Event()
        self._parar = threading.Event()
        self._thread = None

    @property
    def conectado(self):
        return self.estado == "conectado"

    def iniciar(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._laco, daemon=True, name="aula-2.4g")
            self._thread.start()
        return self

    # ---- interface de backend ------------------------------------------------
    def descobrir(self):
        nome = MODELOS.get(self.modelo, "Teclado AULA")
        if self.estado == "conectado":
            return [dsp.Dispositivo(chave=f"{nome} (sem fio)#0", nome=f"{nome} (sem fio)", categoria="Teclado",
                                    estado=dsp.CONECTADO, fabricante="AULA", indice=0,
                                    zonas=[("Teclado", 0, N_LEDS)], limites=[(N_LEDS, N_LEDS)],
                                    matrizes=[MATRIZ], n_leds=N_LEDS, backend=self)]
        if self.estado == "sem_resposta":
            return [dsp.Dispositivo(chave="aula:receptor", nome="Teclado AULA (receptor 2.4G)", categoria="Teclado",
                                    estado=dsp.DESCONECTADO, fabricante="AULA", backend=self,
                                    motivo="O receptor está ligado, mas o teclado não respondeu: ele está no cabo, "
                                           "desligado ou dormindo. Tire o cabo, ligue o modo 2.4G e aperte uma tecla.")]
        if self.estado == "desconhecido":
            return [dsp.Dispositivo(chave="aula:receptor", nome="Teclado AULA (receptor 2.4G)", categoria="Teclado",
                                    estado=dsp.INCOMPATIVEL, fabricante="AULA", backend=self,
                                    motivo=f"O teclado respondeu como modelo {self.modelo:#04x}, que ainda não foi "
                                           "verificado. Para não arriscar, nenhuma cor é enviada a ele.")]
        return []

    def pintar(self, disp, cores):
        if not self.conectado:
            return False
        with self._trava:
            self._quadro = list(cores[:N_LEDS]) + [(0, 0, 0)] * max(0, N_LEDS - len(cores))
        self._novo.set()
        return True

    def redimensionar(self, disp, tamanhos):
        return False

    def fechar(self):
        self._parar.set()
        self._novo.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(2.0)
        self._fechar_h()

    # ---- deteccao ----------------------------------------------------------------
    def _mudar(self, estado, modelo=None):
        if (estado, modelo) != (self.estado, self.modelo):
            self.estado, self.modelo = estado, modelo
            self.versao += 1

    def _fechar_h(self):
        if self._h:
            try:
                self._h.fechar()
            except OSError:
                pass
            self._h = None

    def _consultar(self, h):
        """Modelo informado pelo teclado, ou None se ele nao respondeu."""
        while h.ler(64, 0):                     # descarta o que estiver parado na fila
            pass
        h.escrever(CONSULTA_MODELO)
        fim = time.monotonic() + 1.0
        while time.monotonic() < fim:
            m = resposta_de_modelo(h.ler(64, 250))
            if m is not None:
                return m
        return None

    def _sondar(self):
        try:
            alvos = [e for e in self.hid.listar(VID, PID) if e["pagina"] == PAGINA and e["uso"] == USO]
        except OSError:
            alvos = []
        if not alvos:
            self._mudar("ausente")
            return
        h = None
        try:
            h = self.hid.Aberto(alvos[0]["path"])
            if h.descritor() != DESCRITOR:
                h.fechar()
                self._mudar("ausente")          # outro aparelho com o mesmo ID: nao mexe
                return
            modelo = self._consultar(h)
        except OSError:
            if h:
                h.fechar()
            self._mudar("ausente")
            return
        self.versao_hw = alvos[0]["versao"]
        if modelo is None:
            h.fechar()
            self._mudar("sem_resposta")
        elif modelo in MODELOS:
            self._h = h
            self._ultima_conferencia = time.monotonic()
            self._mudar("conectado", modelo)
        else:
            h.fechar()
            self._mudar("desconhecido", modelo)

    def _conferir(self):
        """Com o teclado conectado: ele ainda responde? Duas faltas seguidas = perdeu."""
        for _ in range(2):
            try:
                if self._consultar(self._h) in MODELOS:
                    return True
            except OSError:
                break
        self._fechar_h()
        self._mudar("sem_resposta")
        return False

    # ---- laco ------------------------------------------------------------------
    def _laco(self):
        prox_sonda = 0.0
        while not self._parar.is_set():
            agora = time.monotonic()
            if not self.conectado:
                if agora >= prox_sonda:
                    self._sondar()
                    prox_sonda = time.monotonic() + SONDAR_A_CADA
                    if self.conectado:
                        continue                # comeca a enviar ja, sem esperar
                self._parar.wait(0.25)
                continue
            if agora - self._ultima_conferencia >= CONFERIR_A_CADA:
                self._ultima_conferencia = agora
                if not self._conferir():
                    continue
            with self._trava:
                quadro = self._quadro
            self._novo.clear()
            if quadro is None:
                self._novo.wait(0.25)
                continue
            inicio = time.monotonic()
            try:
                for r in relatorios_do_quadro(quadro):
                    self._h.escrever(r)
                    self.enviados += 1
                    time.sleep(PAUSA_ENVIO)
            except OSError:
                self._fechar_h()
                self._mudar("sem_resposta")
                prox_sonda = 0.0
                continue
            resta = RENOVAR - (time.monotonic() - inicio)
            if resta > 0:
                self._novo.wait(resta)
