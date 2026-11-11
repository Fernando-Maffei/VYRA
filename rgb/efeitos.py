"""Efeitos por software. Cada efeito e uma funcao pura (contexto, x, y) -> (r, g, b).

x e y sao a posicao do LED na mesa, em 0..1, entao o mesmo efeito funciona em
qualquer periferico e atravessa a mesa inteira na direcao configurada.
"""
import colorsys, math


class Contexto:
    """O que um efeito precisa saber para calcular um quadro."""

    def __init__(self, t, cores, velocidade=50, direcao=0, escala=100, tela=None, pulso=0.0,
                 saturacao=1.3):
        self.t = t
        self.cores = [tuple(c) for c in cores] or [(255, 255, 255)]
        self.vel = velocidade / 50.0                    # 50% = velocidade "normal"
        a = math.radians(direcao)
        self.dx, self.dy = round(math.cos(a), 9), round(math.sin(a), 9)   # 90 graus = 0 exato
        self.escala = max(0.05, escala / 100.0)         # tamanho da onda em "mesas"
        self.tela = tela                                # grade [linha][coluna] de (r, g, b)
        self.pulso = pulso                              # 0..1, sobe ao apertar uma tecla
        self.saturacao = saturacao

    def ao_longo(self, x, y):
        """Posicao do LED ao longo da direcao do efeito, com 0.5 no centro da mesa."""
        return 0.5 + (x - 0.5) * self.dx + (y - 0.5) * self.dy


def mistura(a, b, f):
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f)


def paleta(cores, p):
    """Cor na posicao p (qualquer real) de uma paleta ciclica."""
    n = len(cores)
    if n == 1:
        return cores[0]
    f = (p % 1.0) * n
    i = int(f) % n
    return mistura(cores[i], cores[(i + 1) % n], f - int(f))


def paleta_aberta(cores, p):
    """Como paleta(), mas sem voltar ao inicio: p=0 e a primeira cor, p=1 a ultima."""
    n = len(cores)
    if n == 1:
        return cores[0]
    f = min(max(p, 0.0), 1.0) * (n - 1)
    i = min(int(f), n - 2)
    return mistura(cores[i], cores[i + 1], f - i)


def estatico(c, x, y):
    return c.cores[0]


def arco_iris(c, x, y):
    r, g, b = colorsys.hsv_to_rgb((c.ao_longo(x, y) / c.escala - c.t * c.vel * 0.2) % 1.0, 1.0, 1.0)
    return (r * 255, g * 255, b * 255)


def respiracao(c, x, y):
    fase = c.t * c.vel * 0.25
    nivel = (1 - math.cos(2 * math.pi * fase)) / 2
    cor = c.cores[int(fase) % len(c.cores)]
    return (cor[0] * nivel, cor[1] * nivel, cor[2] * nivel)


def ciclo(c, x, y):
    return paleta(c.cores, c.t * c.vel * 0.1)


def onda(c, x, y):
    return paleta(c.cores, c.ao_longo(x, y) / c.escala - c.t * c.vel * 0.2)


def gradiente(c, x, y):
    return paleta_aberta(c.cores, 0.5 + (c.ao_longo(x, y) - 0.5) / c.escala)


def piscar(c, x, y):
    fase = c.t * c.vel
    return c.cores[int(fase) % len(c.cores)] if fase % 1.0 < 0.5 else (0, 0, 0)


def cometa(c, x, y):
    cauda = 0.35 * c.escala
    cabeca = (c.t * c.vel * 0.3) % (1.0 + cauda)        # atravessa a mesa e a cauda sai junto
    d = cabeca - c.ao_longo(x, y)
    fundo = c.cores[1] if len(c.cores) > 1 else (0, 0, 0)
    if 0 <= d < cauda:
        return mistura(fundo, c.cores[0], (1 - d / cauda) ** 2)
    return fundo


def vai_e_vem(c, x, y):
    largura = 0.12 * c.escala
    fase = (c.t * c.vel * 0.35) % 2.0
    centro = fase if fase <= 1.0 else 2.0 - fase         # onda triangular: vai ate o fim e volta
    d = abs(c.ao_longo(x, y) - centro)
    fundo = c.cores[1] if len(c.cores) > 1 else (0, 0, 0)
    return mistura(fundo, c.cores[0], (1 - d / largura) ** 2) if d < largura else fundo


def preencher(c, x, y):
    fase = c.t * c.vel * 0.25
    k = int(fase)
    nova, velha = c.cores[k % len(c.cores)], c.cores[(k - 1) % len(c.cores)]
    return nova if c.ao_longo(x, y) < fase - k else velha


_BLOCOS = 8


def empilhar(c, x, y):
    """Blocos de luz correm ate o fim e vao se empilhando, ate encher tudo."""
    p = c.ao_longo(x, y)
    fase = (c.t * c.vel * 0.6) % (_BLOCOS + 1.5)         # 1,5 de pausa com tudo cheio
    j = min(int(fase), _BLOCOS)                          # quantos blocos ja estao empilhados
    fundo = (0, 0, 0)
    bloco = min(_BLOCOS - 1, max(0, int((1.0 - p) * _BLOCOS)))   # 0 = o do fim da fila
    if p >= 1.0 - j / _BLOCOS:
        return c.cores[bloco % len(c.cores)]
    if j < _BLOCOS:
        inicio = (fase - j) * (1.0 - (j + 1) / _BLOCOS)  # o bloco da vez viaja ate a pilha
        if inicio <= p < inicio + 1.0 / _BLOCOS:
            return c.cores[j % len(c.cores)]
    return fundo


def reativo(c, x, y):
    fundo = c.cores[1] if len(c.cores) > 1 else (0, 0, 0)
    return mistura(fundo, c.cores[0], c.pulso)


def tela(c, x, y):
    if not c.tela:
        return (0, 0, 0)
    lin, col = len(c.tela), len(c.tela[0])
    r, g, b = c.tela[min(lin - 1, max(0, int(y * lin)))][min(col - 1, max(0, int(x * col)))]
    if c.saturacao != 1.0:                              # a media de uma regiao sai lavada
        cinza = (r + g + b) / 3
        r, g, b = (min(255, max(0, cinza + (v - cinza) * c.saturacao)) for v in (r, g, b))
    return (r, g, b)


# nome mostrado -> (funcao, usa paleta, usa velocidade, usa direcao/escala, descricao)
EFEITOS = {
    "Cor estática": (estatico, True, False, False, "Uma cor fixa (a primeira da paleta)."),
    "Arco-íris": (arco_iris, False, True, True, "Arco-íris que atravessa a mesa na direção escolhida."),
    "Respiração": (respiracao, True, True, False, "Acende e apaga suavemente, trocando de cor a cada ciclo."),
    "Ciclo de cores": (ciclo, True, True, False, "Todos os LEDs passam juntos pelas cores da paleta."),
    "Onda": (onda, True, True, True, "As cores da paleta percorrem a mesa, de um periférico ao outro."),
    "Gradiente": (gradiente, True, False, True, "Degradê parado, da primeira à última cor, ao longo da mesa."),
    "Piscar": (piscar, True, True, False, "Pisca alternando as cores da paleta."),
    "Cometa": (cometa, True, True, True, "Um ponto de luz com cauda percorre tudo; a 2ª cor é o fundo."),
    "Vai e vem": (vai_e_vem, True, True, True, "Uma barra de luz vai até o fim e volta; a 2ª cor é o fundo."),
    "Preencher": (preencher, True, True, True, "Cada cor da paleta vai tomando o lugar da anterior."),
    "Empilhar": (empilhar, True, True, True, "Blocos de luz correm e se empilham até encher tudo."),
    "Reativo": (reativo, True, False, False, "Acende ao pressionar qualquer tecla; a 2ª cor é o fundo."),
    "Tela": (tela, False, False, False, "Cada LED copia a cor da região da tela onde ele está na mesa."),
}


# Combinacoes prontas, aplicadas com um clique. percurso: "sequencia" ou "mesa".
PREDEFINICOES = [
    {"nome": "Meteoro", "efeito": "Cometa", "cores": [[255, 255, 255], [12, 0, 45]],
     "velocidade": 70, "escala": 100, "percurso": "sequencia"},
    {"nome": "Arco-íris contínuo", "efeito": "Arco-íris", "cores": [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
     "velocidade": 50, "escala": 100, "percurso": "sequencia"},
    {"nome": "Corrida neon", "efeito": "Onda", "cores": [[255, 0, 128], [0, 220, 255]],
     "velocidade": 75, "escala": 60, "percurso": "sequencia"},
    {"nome": "Vai e vem", "efeito": "Vai e vem", "cores": [[0, 200, 255], [0, 0, 30]],
     "velocidade": 60, "escala": 100, "percurso": "sequencia"},
    {"nome": "Empilhar", "efeito": "Empilhar", "cores": [[255, 80, 0], [255, 200, 0], [255, 0, 90]],
     "velocidade": 60, "escala": 100, "percurso": "sequencia"},
    {"nome": "Preencher", "efeito": "Preencher", "cores": [[0, 255, 140], [0, 120, 255], [180, 0, 255]],
     "velocidade": 50, "escala": 100, "percurso": "sequencia"},
    {"nome": "Aurora", "efeito": "Onda", "cores": [[0, 255, 150], [0, 120, 255], [120, 0, 255]],
     "velocidade": 25, "escala": 200, "percurso": "sequencia"},
    {"nome": "Fogo", "efeito": "Onda", "cores": [[255, 30, 0], [255, 140, 0], [255, 60, 0]],
     "velocidade": 40, "escala": 50, "percurso": "sequencia"},
    {"nome": "Gelo", "efeito": "Respiração", "cores": [[120, 220, 255], [255, 255, 255]],
     "velocidade": 40, "escala": 100, "percurso": "sequencia"},
    {"nome": "Tela", "efeito": "Tela", "cores": [[255, 255, 255]],
     "velocidade": 50, "escala": 100, "percurso": "mesa"},
    {"nome": "Branco suave", "efeito": "Cor estática", "cores": [[255, 214, 170]],
     "velocidade": 50, "escala": 100, "percurso": "sequencia"},
]


def quadro(nome, ctx, pontos, intensidade=100):
    """Calcula as cores de uma lista de pontos (x, y). Devolve [(r, g, b)] em inteiros."""
    f = EFEITOS.get(nome, EFEITOS["Cor estática"])[0]
    k = max(0.0, min(1.0, intensidade / 100.0))
    saida = []
    for x, y in pontos:
        r, g, b = f(ctx, x, y)
        saida.append((min(255, max(0, int(r * k + 0.5))), min(255, max(0, int(g * k + 0.5))),
                      min(255, max(0, int(b * k + 0.5)))))
    return saida
