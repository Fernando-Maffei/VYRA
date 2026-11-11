"""Cores, fontes e icones da interface. Tudo o que define a aparencia fica aqui."""
from tkinter import ttk

# ---- cores
FUNDO = "#0e1014"           # fundo da janela
LATERAL = "#12151b"         # barra lateral
CARTAO = "#171b22"          # cartoes e paineis
CAMPO = "#1f242d"           # campos, botoes secundarios, item em foco
CAMPO_2 = "#272d38"         # foco sobre campo
LINHA = "#262c37"           # bordas
TEXTO = "#e9ecf2"
SUAVE = "#8a93a6"
APAGADO = "#596174"
DESTAQUE = "#7c6cff"        # violeta
DESTAQUE_2 = "#6a5af0"      # destaque ao passar o mouse
DESTAQUE_FUNDO = "#2a2550"  # fundo de item selecionado
OK, ALERTA, ERRO, NEUTRO = "#3ecf8e", "#f5b83d", "#f0616d", "#6b7280"
MESA = "#0b0d11"

# ---- fontes
F_TEXTO = ("Segoe UI Variable Text", 10)
F_PEQUENA = ("Segoe UI Variable Small", 9)
F_FORTE = ("Segoe UI Variable Text", 10, "bold")
F_NOME = ("Segoe UI Variable Text", 11, "bold")
F_SECAO = ("Segoe UI Variable Small", 8, "bold")
F_TITULO = ("Segoe UI Variable Display", 18, "bold")
F_LOGO = ("Segoe UI Variable Display", 20, "bold")
F_ICONE = "Segoe Fluent Icons"

# ---- icones (Segoe Fluent Icons, ja vem no Windows 11)
I = {
    "dispositivos": "", "efeitos": "", "montagem": "", "tela": "", "ajuda": "",
    "Teclado": "", "Mouse": "", "Mousepad": "", "Headset": "",
    "Fans e coolers": "", "Controladoras": "", "Componentes internos": "", "Outros": "",
    "atualizar": "", "mais": "", "excluir": "", "editar": "", "abrir": "",
    "info": "", "identificar": "", "subir": "", "descer": "", "antes": "",
    "depois": "", "girar": "", "ordenar": "", "ajustes": "", "energia": "",
    "sem_fio": "", "sincronizar": "",
}


def aplicar(raiz):
    """Cores de fundo e estilo dos poucos componentes ttk que restam (rolagem)."""
    raiz.configure(bg=FUNDO)
    s = ttk.Style(raiz)
    s.theme_use("clam")
    for nome in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        s.configure(nome, background=CAMPO, troughcolor=FUNDO, bordercolor=FUNDO, lightcolor=CAMPO,
                    darkcolor=CAMPO, arrowcolor=SUAVE, gripcount=0, arrowsize=11)
        s.map(nome, background=[("active", CAMPO_2)])
    raiz.option_add("*Menu.background", CARTAO)
    raiz.option_add("*Menu.foreground", TEXTO)
    raiz.option_add("*Menu.activeBackground", DESTAQUE)
    raiz.option_add("*Menu.activeForeground", "#ffffff")
    raiz.option_add("*Menu.relief", "flat")
    raiz.option_add("*Menu.font", F_TEXTO)


def hexa(cor):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in cor[:3])


def misturar(a, b, f):
    """Mistura duas cores "#rrggbb"; f=0 da a, f=1 da b."""
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return hexa([x + (y - x) * f for x, y in zip(a, b)])
