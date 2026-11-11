"""luz - controla os LEDs do PC pelo servidor do OpenRGB, sem dependencias.

Quem conversa com o hardware e o OpenRGB. Se ele ja estiver aberto com o
"SDK Server" ligado (porta 6742), o luz usa esse. Se nao estiver, o luz abre o
OpenRGB escondido, aplica a cor e fecha ele em seguida: nada fica rodando.

O luz procura o OpenRGB.exe nas pastas de instalacao comuns. Se o seu estiver
em outro lugar, aponte com --openrgb CAMINHO ou com a variavel LUZ_OPENRGB.

Uso:
  python luz.py listar
  python luz.py cor vermelho
  python luz.py cor "#00ff80" -d teclado --brilho 50
  python luz.py cor 255,120,0 -d 0 -z "Fita ARGB 1"
  python luz.py apagar
  python luz.py efeito arcoiris
  python luz.py efeito respirar azul --velocidade 0.5

-d escolhe o dispositivo (numero ou parte do nome; pode repetir). Sem -d, todos.
-z escolhe a zona (parte do nome). Sem -z, o dispositivo inteiro.
--manter deixa aberto o OpenRGB que o luz abriu.
Os comandos cor/apagar mandam a cor e terminam: nada fica rodando.
Os efeitos rodam ate Ctrl+C (o OpenRGB fica aberto enquanto isso).
"""
import argparse, colorsys, math, os, shutil, socket, struct, subprocess, sys, time

PROTO_MAX = 4  # maior versao do protocolo que este cliente sabe ler

CORES = {
    "vermelho": (255, 0, 0), "verde": (0, 255, 0), "azul": (0, 0, 255),
    "branco": (255, 255, 255), "preto": (0, 0, 0), "amarelo": (255, 255, 0),
    "ciano": (0, 255, 255), "magenta": (255, 0, 255), "roxo": (128, 0, 255),
    "laranja": (255, 100, 0), "rosa": (255, 60, 150),
}


class Erro(Exception):
    pass


class SemServidor(Erro):
    pass


def ler_cor(txt):
    t = txt.strip().lower()
    if t in CORES:
        return CORES[t]
    try:
        if "," in t:
            cor = tuple(int(p) for p in t.split(","))
        else:
            h = t.lstrip("#")
            if len(h) != 6:
                raise ValueError
            cor = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if len(cor) != 3 or not all(0 <= c <= 255 for c in cor):
            raise ValueError
        return cor
    except ValueError:
        raise Erro(f"cor invalida: {txt!r}. Use um nome ({', '.join(CORES)}), "
                   "hexadecimal (ff8000) ou r,g,b (255,128,0)")


class Leitor:
    def __init__(self, dados):
        self.d, self.p = dados, 0

    def n(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.p)[0]
        self.p += struct.calcsize("<" + fmt)
        return v

    def texto(self):
        n = self.n("H")
        t = self.d[self.p:self.p + n]
        self.p += n
        return t.rstrip(b"\0").decode("utf-8", "replace")

    def pula(self, n):
        self.p += n


def ler_dispositivo(dados, v):
    r = Leitor(dados)
    r.n("I")                                # tamanho
    tipo = r.n("i")                         # tipo do dispositivo (teclado, mouse, DRAM...)
    nome = r.texto()
    fabricante = r.texto() if v >= 1 else ""
    for _ in range(4):                      # descricao, versao, serie, local
        r.texto()
    n_modos = r.n("H"); ativo = r.n("i")    # qtd de modos, modo ativo
    modos = [ler_modo(r, v) for _ in range(n_modos)]
    zonas, limites, matrizes, inicio = [], [], [], 0
    for _ in range(r.n("H")):
        znome = r.texto()
        r.n("i")                            # tipo
        limites.append((r.n("I"), r.n("I")))  # leds_min, leds_max (diferentes = ajustavel)
        qtd = r.n("I")
        tam_mapa, fim_mapa = r.n("H"), 0    # mapa da matriz: onde cada LED fica na grade
        fim_mapa = r.p + tam_mapa
        if tam_mapa >= 8:
            alt, larg = r.n("I"), r.n("I")
            if 8 + 4 * alt * larg <= tam_mapa:
                matrizes.append((alt, larg, [r.n("I") for _ in range(alt * larg)]))
            else:
                matrizes.append(None)
        else:
            matrizes.append(None)
        r.p = fim_mapa
        if v >= 4:
            for _ in range(r.n("H")):       # segmentos
                r.texto(); r.pula(12)
        zonas.append((znome, inicio, qtd))
        inicio += qtd
    for _ in range(r.n("H")):               # LEDs
        r.texto(); r.pula(4)
    n_cores = r.n("H")
    cores = [tuple(dados[r.p + 4 * i:r.p + 4 * i + 3]) for i in range(n_cores)]
    return {"nome": nome, "zonas": zonas, "limites": limites, "cores": cores,
            "modos": modos, "modo_ativo": ativo, "tipo": tipo, "fabricante": fabricante,
            "matrizes": matrizes}


# flags de um modo
TEM_VEL, TEM_BRILHO, TEM_COR_LED, TEM_COR_MODO = 1 << 0, 1 << 4, 1 << 5, 1 << 6
GRAVA_MANUAL = 1 << 8


def ler_modo(r, v):
    m = {}
    n = r.n("H")
    m["nome_bruto"] = r.d[r.p:r.p + n]
    r.pula(n)
    m["nome"] = m["nome_bruto"].rstrip(b"\0").decode("utf-8", "replace")
    m["valor"], m["flags"] = r.n("i"), r.n("I")
    m["vel_min"], m["vel_max"] = r.n("I"), r.n("I")
    if v >= 3:
        m["brilho_min"], m["brilho_max"] = r.n("I"), r.n("I")
    m["cores_min"], m["cores_max"] = r.n("I"), r.n("I")
    m["vel"] = r.n("I")
    if v >= 3:
        m["brilho"] = r.n("I")
    m["direcao"], m["modo_cor"] = r.n("I"), r.n("I")
    n = r.n("H")
    m["cores"] = [tuple(r.d[r.p + 4 * i:r.p + 4 * i + 3]) for i in range(n)]
    r.pula(4 * n)
    return m


def empacotar_modo(idx, m, v):
    d = struct.pack("<iH", idx, len(m["nome_bruto"])) + m["nome_bruto"]
    d += struct.pack("<iIII", m["valor"], m["flags"], m["vel_min"], m["vel_max"])
    if v >= 3:
        d += struct.pack("<II", m["brilho_min"], m["brilho_max"])
    d += struct.pack("<III", m["cores_min"], m["cores_max"], m["vel"])
    if v >= 3:
        d += struct.pack("<I", m["brilho"])
    d += struct.pack("<IIH", m["direcao"], m["modo_cor"], len(m["cores"]))
    d += b"".join(bytes((r, g, b, 0)) for r, g, b in m["cores"])
    return struct.pack("<I", 4 + len(d)) + d


class OpenRGB:
    def __init__(self, host, porta, timeout=3.0):
        try:
            self.s = socket.create_connection((host, porta), timeout)
        except OSError as e:
            raise SemServidor(f"nao consegui conectar em {host}:{porta} ({e})")
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.envia(0, 40, struct.pack("<I", PROTO_MAX))
        try:
            self.v = min(struct.unpack("<I", self.espera(40)[:4])[0], PROTO_MAX)
        except socket.timeout:
            self.v = 0                      # servidor antigo: nao responde a versao
        self.envia(0, 50, b"VYRA\0")
        self.envia(0, 0)
        n = struct.unpack("<I", self.espera(0)[:4])[0]
        self.dispositivos = []
        for i in range(n):
            self.envia(i, 1, struct.pack("<I", self.v) if self.v else b"")
            self.dispositivos.append(ler_dispositivo(self.espera(1), self.v))

    def envia(self, dev, pid, dados=b""):
        self.s.sendall(b"ORGB" + struct.pack("<III", dev, pid, len(dados)) + dados)

    def _recebe(self, n):
        b = b""
        while len(b) < n:
            d = self.s.recv(n - len(b))
            if not d:
                raise Erro("o servidor fechou a conexao")
            b += d
        return b

    def espera(self, pid):
        """Le pacotes ate chegar o do tipo pedido; ignora avisos assincronos."""
        while True:
            magic, _, p, tam = struct.unpack("<4sIII", self._recebe(16))
            if magic != b"ORGB":
                raise Erro("resposta invalida: isso nao parece um servidor OpenRGB")
            dados = self._recebe(tam)
            if p == pid:
                return dados

    def modo_direto(self, dev):
        self.envia(dev, 1100)

    def pinta(self, dev, cores):
        corpo = b"".join(bytes((r, g, b, 0)) for r, g, b in cores)
        self.envia(dev, 1050, struct.pack("<IH", 6 + len(corpo), len(cores)) + corpo)

    def atualiza_modo(self, dev, idx, modo):
        """Troca o modo ativo do dispositivo (com velocidade, brilho e cores do modo)."""
        self.envia(dev, 1101, empacotar_modo(idx, modo, self.v))

    def grava_modo(self, dev, idx, modo):
        """Pede ao dispositivo para guardar o modo na memoria dele (protocolo 3+)."""
        if self.v >= 3:
            self.envia(dev, 1102, empacotar_modo(idx, modo, self.v))

    def redimensiona(self, dev, zona, qtd):
        self.envia(dev, 1000, struct.pack("<ii", zona, qtd))

    def recarrega(self, dev):
        self.envia(dev, 1, struct.pack("<I", self.v) if self.v else b"")
        self.dispositivos[dev] = ler_dispositivo(self.espera(1), self.v)
        return self.dispositivos[dev]

    def sincroniza(self):
        """Espera o servidor processar tudo o que ja foi enviado."""
        self.envia(0, 0)
        self.espera(0)

    def fecha(self):
        self.s.close()


def achar_openrgb(caminho):
    if caminho:
        if not os.path.isfile(caminho):
            raise Erro(f"OpenRGB nao encontrado em {caminho!r}")
        return caminho
    candidatos = [os.environ.get("LUZ_OPENRGB"), shutil.which("OpenRGB")]
    for base in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        raiz = os.environ.get(base)
        if raiz:
            candidatos.append(os.path.join(raiz, "OpenRGB", "OpenRGB.exe"))
            candidatos.append(os.path.join(raiz, "Programs", "OpenRGB", "OpenRGB.exe"))
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return None


def abrir_openrgb(exe, host, porta, limite=60.0):
    """Abre o OpenRGB escondido, so como servidor, e espera ele achar os dispositivos."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([exe, "--server", "--server-port", str(porta)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags)
    fim, anterior, iguais = time.monotonic() + limite, -1, 0
    try:
        while time.monotonic() < fim:
            if proc.poll() is not None:
                raise Erro(f"o OpenRGB fechou sozinho logo ao abrir (codigo {proc.returncode})")
            try:
                cli = OpenRGB(host, porta)
            except (Erro, OSError, struct.error):
                time.sleep(0.5)
                continue
            n = len(cli.dispositivos)
            iguais = iguais + 1 if n and n == anterior else 0
            if iguais >= 2:                 # 3 leituras iguais: a deteccao terminou
                return proc, cli
            anterior = n
            cli.fecha()
            time.sleep(1.0)
        raise Erro(f"o OpenRGB abriu, mas nao listou nenhum dispositivo em {limite:.0f}s"
                   if anterior <= 0 else "a lista de dispositivos do OpenRGB nao estabilizou")
    except BaseException:
        fechar_openrgb(proc)
        raise


def fechar_openrgb(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":                     # /T leva junto os processos filhos
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


def escolher(cli, filtros, zona):
    """Devolve [(indice, inicio, qtd)] com o trecho de LEDs de cada dispositivo alvo."""
    alvos = []
    for i, d in enumerate(cli.dispositivos):
        if filtros and not any(f == str(i) or (not f.isdigit() and f.lower() in d["nome"].lower())
                               for f in filtros):
            continue
        if zona is None:
            alvos.append((i, 0, len(d["cores"])))
        else:
            for znome, inicio, qtd in d["zonas"]:
                if zona.lower() in znome.lower():
                    alvos.append((i, inicio, qtd))
    if not alvos:
        raise Erro("nenhum dispositivo/zona combina com o filtro. Veja: python luz.py listar")
    return alvos


def escala(cor, brilho):
    return tuple(round(c * brilho / 100) for c in cor)


def aplicar(cli, alvos, gerar):
    """gerar(k, qtd) -> cor do LED k de um trecho com qtd LEDs."""
    quadros = {}
    for i, inicio, qtd in alvos:
        q = quadros.setdefault(i, list(cli.dispositivos[i]["cores"]))
        q[inicio:inicio + qtd] = [gerar(k, qtd) for k in range(qtd)]
    for i, q in quadros.items():
        cli.pinta(i, q)
        cli.dispositivos[i]["cores"] = q


def cmd_listar(cli, a):
    print(f"protocolo {cli.v}, {len(cli.dispositivos)} dispositivo(s)")
    for i, d in enumerate(cli.dispositivos):
        print(f"[{i}] {d['nome']} - {len(d['cores'])} LEDs")
        for znome, _, qtd in d["zonas"]:
            print(f"      zona {znome!r}: {qtd} LEDs")


def cmd_cor(cli, a):
    cor = escala(ler_cor(a.cor), a.brilho)
    alvos = escolher(cli, a.dispositivo, a.zona)
    for i in {i for i, _, _ in alvos}:
        cli.modo_direto(i)
    aplicar(cli, alvos, lambda k, qtd: cor)
    print("cor %d,%d,%d aplicada em %d dispositivo(s)" % (*cor, len({i for i, _, _ in alvos})))


def cmd_efeito(cli, a):
    base = ler_cor(a.cor)
    alvos = escolher(cli, a.dispositivo, a.zona)
    for i in {i for i, _, _ in alvos}:
        cli.modo_direto(i)
    print(f"efeito {a.tipo} rodando a {a.fps} quadros/s (Ctrl+C para parar)", flush=True)
    t0, passo = time.monotonic(), 1.0 / a.fps
    try:
        while True:
            t = (time.monotonic() - t0) * a.velocidade
            if a.segundos and time.monotonic() - t0 >= a.segundos:
                break
            if a.tipo == "arcoiris":
                def gerar(k, qtd):
                    r, g, b = colorsys.hsv_to_rgb((t * 0.2 + k / max(qtd, 1)) % 1.0, 1.0, 1.0)
                    return escala((r * 255, g * 255, b * 255), a.brilho)
            else:  # respirar
                nivel = (1 - math.cos(t * math.pi)) / 2
                cor = escala(base, a.brilho * nivel)
                def gerar(k, qtd):
                    return cor
            aplicar(cli, alvos, gerar)
            time.sleep(passo)
    except KeyboardInterrupt:
        print("parado")


def main():
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--host", default="127.0.0.1")
    comum.add_argument("--porta", type=int, default=6742)
    comum.add_argument("-d", "--dispositivo", action="append", default=[],
                       help="numero ou parte do nome (pode repetir)")
    comum.add_argument("-z", "--zona", help="parte do nome da zona")
    comum.add_argument("--brilho", type=float, default=100, help="0 a 100")
    comum.add_argument("--openrgb", help="caminho do OpenRGB.exe, para abrir se nao estiver rodando")
    comum.add_argument("--manter", action="store_true",
                       help="nao fecha o OpenRGB que o luz abriu")

    p = argparse.ArgumentParser(prog="luz", description="VYRA - controla LEDs pelo servidor do OpenRGB.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar", parents=[comum], help="mostra dispositivos e zonas").set_defaults(f=cmd_listar)
    c = sub.add_parser("cor", parents=[comum], help="aplica uma cor fixa")
    c.add_argument("cor", help="nome, hexadecimal (ff8000) ou r,g,b")
    c.set_defaults(f=cmd_cor)
    sub.add_parser("apagar", parents=[comum], help="apaga os LEDs").set_defaults(f=cmd_cor, cor="preto")
    e = sub.add_parser("efeito", parents=[comum], help="efeito animado (roda ate Ctrl+C)")
    e.add_argument("tipo", choices=["arcoiris", "respirar"])
    e.add_argument("cor", nargs="?", default="branco", help="cor do respirar")
    e.add_argument("--fps", type=float, default=20)
    e.add_argument("--velocidade", type=float, default=1.0)
    e.add_argument("--segundos", type=float, default=0, help="para sozinho depois desse tempo")
    e.set_defaults(f=cmd_efeito)
    a = p.parse_args()

    try:
        if not 0 <= a.brilho <= 100:
            raise Erro("--brilho deve ficar entre 0 e 100")
        if a.cmd == "efeito" and not 1 <= a.fps <= 60:
            raise Erro("--fps deve ficar entre 1 e 60")
        if a.cmd in ("cor", "apagar", "efeito"):
            ler_cor(a.cor)                  # valida antes de conectar
        proc = None
        try:
            cli = OpenRGB(a.host, a.porta)
        except SemServidor as e:
            exe = achar_openrgb(a.openrgb)
            if a.host not in ("127.0.0.1", "localhost") or not exe:
                raise Erro(f"{e}.\nO OpenRGB nao esta rodando e nao achei o OpenRGB.exe para abrir. "
                           "Instale o OpenRGB ou aponte com --openrgb CAMINHO.")
            print("abrindo o OpenRGB...", flush=True)
            proc, cli = abrir_openrgb(exe, a.host, a.porta)
        try:
            a.f(cli, a)
            if proc and not a.manter:
                cli.sincroniza()
                time.sleep(0.5)             # folga para a cor chegar ao hardware
        finally:
            cli.fecha()
            if proc and not a.manter:
                fechar_openrgb(proc)
                print("OpenRGB fechado")
    except Erro as e:
        sys.exit(f"luz: {e}")
    except socket.timeout:
        sys.exit("luz: o servidor parou de responder")
    except (OSError, struct.error) as e:
        sys.exit(f"luz: falha na comunicacao com o servidor ({type(e).__name__}: {e})")


if __name__ == "__main__":
    main()
