"""Montagem e mesa: o que esta ligado em cada canal, onde fica e em que ordem.

Tres ideias separadas:
  - montagem: o que existe fisicamente em cada zona/canal ("3 fans de 16 LEDs",
    "uma fita"). Vale para todos os layouts. Divide a zona em PECAS.
  - mesa: onde cada peca fica (x, y, tamanho, rotacao). Usada pelos efeitos
    "pela posicao" e pelo efeito Tela.
  - sequencia: a ordem das pecas, uma depois da outra. Usada pelos efeitos
    "em sequencia", em que a luz sai de uma fan e entra na proxima.
Um layout guarda a mesa e a sequencia: {"pecas": {id: colocacao}, "ordem": [id]}.
"""
import math

LARGURA, ALTURA = 1000.0, 600.0
TIPOS = {"fan": "Fans ou anéis (círculo)", "fita": "Fita ou barra (linha)", "vazio": "Nada ligado"}
AUTO_MAX = 126          # "todos os LEDs" de um canal: o limite do canal, sem passar disto


def quantidades(disp, montagem, tamanhos):
    """{zona: LEDs} que cada canal ajustavel deve ter, pela montagem.

    Sem nada configurado o canal ja vem com todos os LEDs (o limite dele). So vale um
    numero especifico quando a montagem diz "especifico" ou ha um tamanho salvo antigo.
    """
    mont, salvos = montagem.get(disp.chave, {}), tamanhos.get(disp.chave, {})
    saida = {}
    for _, zn, _, (lo, hi) in disp.zonas_ajustaveis:
        m = mont.get(zn)
        todos = max(lo, min(hi, AUTO_MAX))
        if m is None:
            saida[zn] = int(salvos[zn]) if zn in salvos else todos
        elif m.get("tipo") == "vazio":
            saida[zn] = lo
        elif m.get("especifico"):
            n = int(m.get("fans") or 1) * int(m.get("por_fan") or 0) if m.get("tipo") == "fan" \
                else int(m.get("leds") or 0)
            saida[zn] = max(lo, min(hi, n))
        else:
            saida[zn] = todos
    return saida


class Peca:
    """Um trecho continuo de LEDs de um dispositivo: uma fan, uma fita, um pente de memoria."""
    __slots__ = ("id", "dev", "zona", "nome", "curto", "inicio", "qtd", "forma", "matriz")

    def __init__(self, **campos):
        for k, v in campos.items():
            setattr(self, k, v)


def layout_vazio():
    return {"pecas": {}, "ordem": []}


def pecas(dispositivos, montagem):
    """Divide os dispositivos em pecas conforme a montagem."""
    saida = []
    for d in dispositivos:
        if not d.n_leds:
            continue
        mont = montagem.get(d.chave, {})
        com_leds = [z for z in d.zonas if z[2] > 0]
        for zi, (zn, inicio, qtd) in enumerate(d.zonas):
            if qtd <= 0:
                continue
            m = mont.get(zn, {})
            mat = d.matrizes[zi] if zi < len(d.matrizes) else None
            base = d.nome if len(d.zonas) == 1 else f"{d.nome} · {zn}"
            curto = d.nome if len(d.zonas) == 1 else zn
            por = int(m.get("por_fan") or 0) if m.get("especifico", True) else 0
            if m.get("tipo") == "fan" and por > 0:
                n = math.ceil(qtd / por)
                for k in range(n):
                    saida.append(Peca(id=f"{d.chave}|{zn}|{k}", dev=d.chave, zona=zn,
                                      nome=f"{base} · fan {k + 1}" if n > 1 else base,
                                      curto=f"{curto} #{k + 1}" if n > 1 else curto,
                                      inicio=inicio + k * por, qtd=min(por, qtd - k * por),
                                      forma="anel", matriz=None))
            else:
                forma = "anel" if m.get("tipo") == "fan" else ("matriz" if mat else "linha")
                saida.append(Peca(id=f"{d.chave}|{zn}|0", dev=d.chave, zona=zn, nome=base, curto=curto,
                                  inicio=inicio, qtd=qtd, forma=forma, matriz=mat))
    return saida


def _tamanho(p):
    return {"anel": (110.0, 110.0), "matriz": (300.0, 110.0)}.get(p.forma, (200.0, 36.0))


def _vaga(k):
    """Posicao da k-esima vaga livre, em fileiras."""
    por_linha, passo_x, passo_y = 7, 135.0, 135.0
    return 30.0 + (k % por_linha) * passo_x, 30.0 + (k // por_linha) * passo_y


def completar(lay, ps):
    """Garante colocacao e lugar na ordem para cada peca, sem mexer no que ja existe."""
    lay.setdefault("pecas", {})
    lay.setdefault("ordem", [])
    for p in ps:
        if p.id not in lay["pecas"]:
            w, h = _tamanho(p)
            x, y = _vaga(len(lay["pecas"]))
            lay["pecas"][p.id] = {"x": x, "y": y, "w": w, "h": h, "rot": 0.0, "invertido": False}
        if p.id not in lay["ordem"]:
            lay["ordem"].append(p.id)
    return lay


def em_ordem(lay, ps):
    """As pecas presentes, na ordem da sequencia."""
    por_id = {p.id: p for p in ps}
    vistos, saida = set(), []
    for i in lay.get("ordem", ()):
        if i in por_id and i not in vistos:
            vistos.add(i)
            saida.append(por_id[i])
    return saida + [p for p in ps if p.id not in vistos]


def organizar_em_fila(lay, ps):
    """Coloca as pecas lado a lado, na ordem da sequencia, quebrando em fileiras."""
    x, y, alto = 30.0, 40.0, 0.0
    for p in em_ordem(lay, ps):
        c = lay["pecas"][p.id]
        w, h = _tamanho(p)
        if x + w > LARGURA - 20:
            x, y, alto = 30.0, y + alto + 45.0, 0.0
        c.update(x=x, y=y, w=w, h=h, rot=0.0)
        x, alto = x + w + 25.0, max(alto, h)


def ordenar_pela_posicao(lay, ps):
    """Refaz a sequencia pela posicao na mesa: de cima para baixo, da esquerda para a direita."""
    def centro(p):
        c = lay["pecas"][p.id]
        return c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
    presentes, fileira, topo = [], [], None
    for p in sorted(ps, key=lambda p: centro(p)[1]):     # junta em fileiras o que esta na mesma altura
        y = centro(p)[1]
        if topo is not None and y - topo > 70:
            presentes += sorted(fileira, key=lambda q: centro(q)[0])
            fileira = []
        if not fileira:
            topo = y
        fileira.append(p)
    presentes += sorted(fileira, key=lambda q: centro(q)[0])
    ausentes = [i for i in lay["ordem"] if i not in {p.id for p in ps}]
    lay["ordem"] = [p.id for p in presentes] + ausentes


def _locais(p):
    """Posicao (u, v) em 0..1 de cada LED dentro do retangulo da peca."""
    n = p.qtd
    if p.forma == "anel":
        return [(0.5 + 0.5 * math.cos(2 * math.pi * i / n - math.pi / 2),
                 0.5 + 0.5 * math.sin(2 * math.pi * i / n - math.pi / 2)) for i in range(n)]
    if p.forma == "matriz" and p.matriz:
        alt, larg, mapa = p.matriz
        pts = [(0.5, 0.5)] * n
        for celula, led in enumerate(mapa):
            if led < n:
                lin, col = divmod(celula, larg)
                pts[led] = ((col + 0.5) / larg, (lin + 0.5) / alt)
        return pts
    return [((i + 0.5) / n, 0.5) for i in range(n)]


def posicoes(p, c):
    """Posicao de cada LED da peca na mesa (0..LARGURA, 0..ALTURA), na ordem dos LEDs."""
    cx, cy = c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
    a = math.radians(c.get("rot", 0.0))
    cos, sen = math.cos(a), math.sin(a)
    locais = _locais(p)
    if c.get("invertido") and p.forma != "matriz":
        locais = locais[::-1]               # mesmo desenho, sentido contrario
    saida = []
    for u, v in locais:
        dx, dy = (u - 0.5) * c["w"], (v - 0.5) * c["h"]
        saida.append((cx + dx * cos - dy * sen, cy + dx * sen + dy * cos))
    return saida


def pontos_mesa(p, lay):
    """(x, y) em 0..1 de cada LED da peca, pela posicao dela na mesa."""
    c = lay["pecas"].get(p.id)
    if c is None:
        return [(0.5, 0.5)] * p.qtd
    return [(x / LARGURA, y / ALTURA) for x, y in posicoes(p, c)]


def pontos_sequencia(ps, lay):
    """{id da peca: [(s, 0.5)]}: s em 0..1 ao longo da fila formada pelas pecas dadas."""
    fila = em_ordem(lay, ps)
    total = sum(p.qtd for p in fila) or 1
    saida, feito = {}, 0
    for p in fila:
        pts = [((feito + i + 0.5) / total, 0.5) for i in range(p.qtd)]
        if lay["pecas"].get(p.id, {}).get("invertido"):
            pts.reverse()
        saida[p.id] = pts
        feito += p.qtd
    return saida


def cantos(c):
    """Os 4 cantos do retangulo girado, para desenhar na mesa."""
    cx, cy = c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
    a = math.radians(c.get("rot", 0.0))
    cos, sen = math.cos(a), math.sin(a)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = sx * c["w"] / 2, sy * c["h"] / 2
        pts.append((cx + dx * cos - dy * sen, cy + dx * sen + dy * cos))
    return pts


def contem(c, x, y):
    """O ponto (x, y) da mesa esta dentro do retangulo girado?"""
    cx, cy = c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
    a = -math.radians(c.get("rot", 0.0))
    dx, dy = x - cx, y - cy
    lx, ly = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    return abs(lx) <= c["w"] / 2 and abs(ly) <= c["h"] / 2
