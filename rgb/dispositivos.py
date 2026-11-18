"""Descoberta e comunicacao com os perifericos, independente de fabricante.

Um backend sabe achar dispositivos e mandar cores. O principal e o BackendOpenRGB;
os "extras" cobrem o que o OpenRGB nao controla (hoje: teclado AULA no receptor 2.4G,
em rgb/aula.py). Cada dispositivo sabe qual backend o controla.
Dispositivos que o Windows enxerga mas nenhum backend controla aparecem como
"incompativel", com o motivo, em vez de serem escondidos ou simulados.
"""
import json, os, socket, subprocess, threading

import luz

CATEGORIAS = ["Teclado", "Mouse", "Mousepad", "Headset", "Fans e coolers",
              "Controladoras", "Componentes internos", "Outros"]

# tipo de dispositivo do protocolo OpenRGB -> categoria da interface
_CATEGORIA_POR_TIPO = {5: "Teclado", 18: "Teclado", 6: "Mouse", 7: "Mousepad", 8: "Headset",
                       9: "Headset", 3: "Fans e coolers", 4: "Controladoras",
                       0: "Componentes internos", 1: "Componentes internos",
                       2: "Componentes internos", 14: "Componentes internos",
                       15: "Componentes internos"}

CONECTADO, SEM_LEDS, INCOMPATIVEL, DESCONECTADO = "conectado", "sem_leds", "incompativel", "desconectado"

# Perifericos que o Windows mostra mas que nao conseguimos controlar, e por que.
# (vid, pid ou None para qualquer, nome, categoria, palavras que indicam que um backend ja o controla, motivo)
_LOGITECH = ("O OpenRGB não está controlando o mouse. Com o Logitech G HUB aberto (inclusive o serviço "
             "logi_lamparray_service) os dois disputam o mouse: feche o G HUB por completo e reinicie o "
             "OpenRGB. Sem fio, o OpenRGB também precisa ser reiniciado depois que o cabo é retirado.")
USB_SEM_CONTROLE = [
    ("046D", "C090", "Logitech G703 LIGHTSPEED", "Mouse", ("g703", "logitech"), _LOGITECH),
    ("046D", "C539", "Logitech G703 LIGHTSPEED", "Mouse", ("g703", "logitech"), _LOGITECH),
    ("3554", "FA09", "Teclado AULA (receptor 2.4G)", "Teclado", ("aula", "sinowealth"),
     "O receptor sem fio 3554:FA09 não tem suporte no OpenRGB e o controle próprio para ele não "
     "pôde ser carregado (falta a hidapi do OpenRGB). Pelo cabo USB o teclado funciona."),
]


class Dispositivo:
    def __init__(self, chave, nome, categoria, estado, fabricante="", indice=None,
                 zonas=(), limites=(), matrizes=(), n_leds=0, motivo="", backend=None):
        self.chave = chave              # identificador estavel, usado em perfis e layouts
        self.nome = nome
        self.categoria = categoria
        self.estado = estado
        self.fabricante = fabricante
        self.indice = indice            # posicao no backend (None se nao controlavel)
        self.zonas = list(zonas)        # [(nome, inicio, quantidade)]
        self.limites = list(limites)    # [(min, max)] por zona; diferentes = quantidade ajustavel
        self.matrizes = list(matrizes)  # [None ou (altura, largura, mapa)] por zona
        self.n_leds = n_leds
        self.motivo = motivo
        self.backend = backend          # quem manda as cores (None = o backend principal)

    @property
    def controlavel(self):
        return self.estado == CONECTADO and self.n_leds > 0

    @property
    def zonas_ajustaveis(self):
        return [(i, z[0], z[2], lim) for i, (z, lim) in enumerate(zip(self.zonas, self.limites))
                if lim[0] != lim[1]]


class BackendOpenRGB:
    nome = "OpenRGB"

    def __init__(self, host="127.0.0.1", porta=6742):
        self.host, self.porta = host, porta
        self.cli = None
        self.trava = threading.RLock()      # a interface e o motor usam o mesmo socket
        self.preparados = set()

    @property
    def conectado(self):
        return self.cli is not None

    def conectar(self):
        """Abre (ou reabre) a conexao. Levanta luz.Erro se o servidor nao estiver no ar."""
        try:                                # teste rapido: no Windows uma porta fechada demora ~2 s para recusar
            socket.create_connection((self.host, self.porta), 0.3).close()
        except OSError as e:
            raise luz.SemServidor(f"sem servidor em {self.host}:{self.porta} ({e})")
        novo = luz.OpenRGB(self.host, self.porta)
        with self.trava:
            antigo, self.cli = self.cli, novo
            self.preparados.clear()
        if antigo:
            antigo.fecha()

    def _perdeu(self):
        with self.trava:
            if self.cli:
                try:
                    self.cli.fecha()
                except OSError:
                    pass
            self.cli = None
            self.preparados.clear()

    def descobrir(self):
        with self.trava:
            if not self.cli:
                return []
            dados = list(self.cli.dispositivos)
        vistos, saida = {}, []
        for i, d in enumerate(dados):
            k = vistos.get(d["nome"], 0)
            vistos[d["nome"]] = k + 1
            n = len(d["cores"])
            saida.append(Dispositivo(
                chave=f"{d['nome']}#{k}", nome=d["nome"],
                categoria=_CATEGORIA_POR_TIPO.get(d.get("tipo"), "Outros"),
                estado=CONECTADO if n else SEM_LEDS, fabricante=d.get("fabricante", ""), indice=i,
                zonas=d["zonas"], limites=d["limites"], matrizes=d.get("matrizes", ()), n_leds=n, backend=self,
                motivo="" if n else "Informe quantos LEDs há em cada canal para poder controlar."))
        return saida

    def pintar(self, disp, cores):
        """Envia um quadro. Devolve False se a conexao caiu (o motor tenta reconectar depois)."""
        with self.trava:
            if not self.cli or disp.indice is None:
                return False
            try:
                if disp.indice not in self.preparados:
                    self.cli.modo_direto(disp.indice)
                    self.preparados.add(disp.indice)
                self.cli.pinta(disp.indice, cores)
                return True
            except (OSError, luz.Erro):
                self._perdeu()
                return False

    def redimensionar(self, disp, tamanhos):
        """tamanhos: {nome da zona: quantidade}. Devolve True se algo mudou."""
        with self.trava:
            if not self.cli or disp.indice is None:
                return False
            mudou = False
            for zi, znome, qtd, (lo, hi) in disp.zonas_ajustaveis:
                novo = tamanhos.get(znome)
                if novo is None:
                    continue
                novo = max(lo, min(hi, int(novo)))
                if novo != qtd:
                    self.cli.redimensiona(disp.indice, zi, novo)
                    mudou = True
            if mudou:
                self.cli.recarrega(disp.indice)
                self.preparados.discard(disp.indice)
            return mudou

    def fechar(self):
        self._perdeu()


def usb_presentes(timeout=20):
    """Pares (VID, PID) dos dispositivos USB presentes, via PowerShell. Vazio se falhar."""
    cmd = ("Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
           "Where-Object { $_.InstanceId -match '^USB\\\\VID_' } | "
           "ForEach-Object { $_.InstanceId } | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ids = json.loads(r.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return set()
    if isinstance(ids, str):
        ids = [ids]
    pares = set()
    for i in ids:
        try:
            vid = i.split("VID_")[1][:4].upper()
            pid = i.split("PID_")[1][:4].upper()
            pares.add((vid, pid))
        except IndexError:
            pass
    return pares


def sem_controle(presentes, controlados):
    """Dispositivos da tabela USB_SEM_CONTROLE que estao plugados e que nenhum backend controla."""
    nomes = " ".join(d.nome.lower() for d in controlados)
    saida, vistos = [], set()
    for vid, pid, nome, cat, pistas, motivo in USB_SEM_CONTROLE:
        if (vid, pid) not in presentes or nome in vistos:
            continue
        if any(p in nomes for p in pistas):
            continue                        # um backend ja controla este periferico
        vistos.add(nome)
        saida.append(Dispositivo(chave=f"usb:{nome}", nome=nome, categoria=cat,
                                 estado=INCOMPATIVEL, motivo=motivo))
    return saida


class Gerenciador:
    """Junta o que os backends controlam com o que so foi visto no USB."""

    def __init__(self, backend, extras=()):
        self.backend = backend          # principal (OpenRGB), com conexao cuidada pelo motor
        self.extras = list(extras)      # cuidam da propria deteccao, em threads proprias
        self.dispositivos = []
        self.usb = set()

    def atualizar(self, ler_usb=False):
        if ler_usb:
            self.usb = usb_presentes()
        controlados = self.backend.descobrir()
        for e in self.extras:
            controlados = controlados + e.descobrir()
        self.dispositivos = controlados + sem_controle(self.usb, controlados)
        return self.dispositivos

    def pintar(self, disp, cores):
        return (disp.backend or self.backend).pintar(disp, cores)

    def fechar(self):
        self.backend.fechar()
        for e in self.extras:
            e.fechar()

    def por_chave(self, chave):
        return next((d for d in self.dispositivos if d.chave == chave), None)

    def controlaveis(self):
        return [d for d in self.dispositivos if d.controlavel]


def gerenciador_padrao(host="127.0.0.1", porta=6742):
    """OpenRGB mais os controladores proprios (AULA 2.4G, fitas LotusLamp X) que puderem ser carregados neste PC.

    LUZ_SEM_EXTRAS=1 desliga os extras (usado nos testes, para nao tocar no hardware real).
    """
    extras = []
    if not os.environ.get("LUZ_SEM_EXTRAS"):
        try:
            from . import aula, hid
            if hid.disponivel():
                extras.append(aula.BackendAULA().iniciar())
        except (ImportError, OSError):
            pass
        try:
            from . import lotus
            if lotus.disponivel():
                extras.append(lotus.BackendLotus().iniciar())
        except (ImportError, OSError):
            pass
    return Gerenciador(BackendOpenRGB(host, porta), extras)
