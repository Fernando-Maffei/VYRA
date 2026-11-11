"""Componentes proprios, desenhados em Canvas, para fugir da aparencia padrao do Tk.

Os que podem ser desligados aceitam state(["disabled"]) / state(["!disabled"]) e
instate(["disabled"]), como os do ttk, para o resto do codigo nao precisar saber
a diferenca.
"""
import tkinter as tk
import tkinter.font as tkfont

from . import tema as T


def fundo_de(w):
    try:
        return w.cget("bg")
    except tk.TclError:
        return T.FUNDO


def retangulo(c, x1, y1, x2, y2, r, **kw):
    """Retangulo de cantos arredondados num Canvas."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    p = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
         x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(p, smooth=True, **kw)


class _Estado:
    """state()/instate() no estilo ttk, so com "disabled"."""
    _desligado = False

    def state(self, specs=None):
        if specs:
            for s in specs:
                if s in ("disabled", "!disabled"):
                    self._desligado = s == "disabled"
            self._redesenhar()
        return ("disabled",) if self._desligado else ()

    def instate(self, specs):
        return all((s == "disabled") == self._desligado for s in specs if s in ("disabled", "!disabled"))

    def _redesenhar(self):
        pass


def _clicavel(widgets, comando, cursor="hand2"):
    for w in widgets:
        w.bind("<Button-1>", lambda e: comando())
        w.configure(cursor=cursor)


# ---------------------------------------------------------------------------
class Botao(_Estado, tk.Canvas):
    """Botao arredondado. tipo: "primario", "secundario" ou "fantasma"."""
    CORES = {"primario": (T.DESTAQUE, T.DESTAQUE_2, "#ffffff"),
             "secundario": (T.CAMPO, T.CAMPO_2, T.TEXTO),
             "fantasma": (None, T.CAMPO, T.TEXTO),
             "perigo": (None, "#3a1d22", T.ERRO)}

    def __init__(self, pai, texto="", comando=None, tipo="secundario", icone=None, altura=32,
                 largura=None, fonte=None, dica=None):
        self.fonte = tkfont.Font(font=fonte or T.F_TEXTO)
        self.ifonte = tkfont.Font(family=T.F_ICONE, size=11)
        self.texto, self.icone, self.tipo, self.comando = texto, icone, tipo, comando
        w = largura or (self.fonte.measure(texto) + (24 if texto else 0) + (22 if icone else 0) + (12 if not texto else 0))
        super().__init__(pai, width=max(w, altura), height=altura, bg=fundo_de(pai), highlightthickness=0,
                         cursor="hand2")
        self._sobre = False
        self.bind("<Enter>", lambda e: self._sobre_mouse(True))
        self.bind("<Leave>", lambda e: self._sobre_mouse(False))
        self.bind("<ButtonRelease-1>", self._clique)
        self.bind("<Configure>", lambda e: self._redesenhar())
        if dica:
            Dica(self, dica)
        self._redesenhar()

    def _sobre_mouse(self, sim):
        self._sobre = sim
        self._redesenhar()

    def _clique(self, e):
        if not self._desligado and self.comando and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.comando()

    def configurar(self, texto=None, tipo=None):
        if texto is not None:
            self.texto = texto
        if tipo is not None:
            self.tipo = tipo
        self._redesenhar()

    def _redesenhar(self):
        self.delete("all")
        w, h = int(self.cget("width")), int(self.cget("height"))
        base, sobre, cor_txt = self.CORES[self.tipo]
        preench = sobre if (self._sobre and not self._desligado) else base
        if self._desligado:
            preench, cor_txt = (T.CAMPO if base else None), T.APAGADO
        if preench:
            retangulo(self, 1, 1, w - 1, h - 1, 8, fill=preench, outline="")
        self.configure(cursor="arrow" if self._desligado else "hand2")
        largura_txt = self.fonte.measure(self.texto) if self.texto else 0
        x = (w - largura_txt - (22 if self.icone and self.texto else 0)) / 2
        if self.icone:
            self.create_text(x + (8 if self.texto else (w / 2 - x)), h / 2 + 1, text=self.icone, font=self.ifonte,
                             fill=cor_txt)
            x += 22
        if self.texto:
            self.create_text(x, h / 2, text=self.texto, font=self.fonte, fill=cor_txt, anchor="w")


# ---------------------------------------------------------------------------
class Interruptor(_Estado, tk.Frame):
    """Chave liga/desliga com texto opcional. variable: BooleanVar."""

    def __init__(self, pai, texto="", variable=None, comando=None, fonte=None, cor_texto=None):
        bg = fundo_de(pai)
        super().__init__(pai, bg=bg)
        self.var = variable or tk.BooleanVar()
        self.comando = comando
        self.c = tk.Canvas(self, width=38, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.c.pack(side="left")
        self.rot = None
        self._cor_texto = cor_texto or T.TEXTO
        if texto:
            self.rot = tk.Label(self, text=texto, bg=bg, fg=self._cor_texto, font=fonte or T.F_TEXTO, cursor="hand2",
                                justify="left", anchor="w")
            self.rot.pack(side="left", padx=(9, 0))
        for w in (self.c, self.rot) if self.rot else (self.c,):
            w.bind("<Button-1>", lambda e: self.alternar())
        self.var.trace_add("write", lambda *a: self._redesenhar())
        self._redesenhar()

    def alternar(self):
        if self._desligado:
            return
        self.var.set(not self.var.get())
        if self.comando:
            self.comando()

    def _redesenhar(self):
        c = self.c
        if not c.winfo_exists():
            return
        c.delete("all")
        ligado = bool(self.var.get())
        trilho = (T.DESTAQUE if ligado else T.CAMPO_2) if not self._desligado else T.CAMPO
        retangulo(c, 1, 2, 37, 20, 9, fill=trilho, outline="")
        x = 27 if ligado else 11
        c.create_oval(x - 6, 5, x + 6, 17, fill="#ffffff" if not self._desligado else T.APAGADO, outline="")
        if self.rot:
            self.rot.configure(fg=T.APAGADO if self._desligado else self._cor_texto)


# ---------------------------------------------------------------------------
class Deslizador(_Estado, tk.Frame):
    """Barra deslizante com nome e valor. comando(valor_inteiro) so e chamado pelo usuario."""

    def __init__(self, pai, texto, de=0, ate=100, variable=None, comando=None, largura=260, sufixo="%",
                 mostrar=None):
        bg = fundo_de(pai)
        super().__init__(pai, bg=bg)
        self.de, self.ate, self.sufixo, self.comando, self.largura = de, ate, sufixo, comando, largura
        self.mostrar = mostrar or (lambda v: f"{v}{sufixo}")
        self.var = variable or tk.DoubleVar(value=de)
        topo = tk.Frame(self, bg=bg)
        topo.pack(fill="x")
        self.rot = tk.Label(topo, text=texto, bg=bg, fg=T.SUAVE, font=T.F_PEQUENA)
        self.rot.pack(side="left")
        self.rot_valor = tk.Label(topo, bg=bg, fg=T.TEXTO, font=T.F_PEQUENA)
        self.rot_valor.pack(side="right")
        self.c = tk.Canvas(self, width=largura, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.c.pack(fill="x")
        self.c.bind("<Button-1>", self._arrastar)
        self.c.bind("<B1-Motion>", self._arrastar)
        self.c.bind("<MouseWheel>", self._roda)
        self.c.bind("<Configure>", lambda e: self._redesenhar())
        self.var.trace_add("write", lambda *a: self._redesenhar())
        self._redesenhar()

    @property
    def valor(self):
        try:
            return int(round(float(self.var.get())))
        except (tk.TclError, ValueError):
            return self.de

    def _definir(self, v):
        v = int(round(max(self.de, min(self.ate, v))))
        if v != self.valor:
            self.var.set(v)
            if self.comando:
                self.comando(v)

    def _arrastar(self, e):
        if self._desligado:
            return
        w = max(1, self.c.winfo_width() - 16)
        self._definir(self.de + (self.ate - self.de) * (e.x - 8) / w)

    def _roda(self, e):
        if self._desligado:
            return "break"
        passo = max(1, (self.ate - self.de) // 50)
        self._definir(self.valor + (passo if e.delta > 0 else -passo))
        return "break"

    def _redesenhar(self):
        c = self.c
        if not c.winfo_exists():
            return
        c.delete("all")
        w = max(c.winfo_width(), 40) if c.winfo_ismapped() else self.largura
        f = (self.valor - self.de) / max(1, self.ate - self.de)
        x = 8 + f * (w - 16)
        cor = T.APAGADO if self._desligado else T.DESTAQUE
        retangulo(c, 8, 9, w - 8, 13, 2, fill=T.CAMPO_2, outline="")
        if x > 9:
            retangulo(c, 8, 9, x, 13, 2, fill=cor, outline="")
        c.create_oval(x - 7, 4, x + 7, 18, fill="#ffffff" if not self._desligado else T.CAMPO_2, outline=cor, width=2)
        self.rot_valor.configure(text=self.mostrar(self.valor), fg=T.APAGADO if self._desligado else T.TEXTO)
        self.rot.configure(fg=T.APAGADO if self._desligado else T.SUAVE)
        c.configure(cursor="arrow" if self._desligado else "hand2")


# ---------------------------------------------------------------------------
class Segmentado(_Estado, tk.Frame):
    """Escolha entre poucas opcoes lado a lado. opcoes: [(valor, texto)]; variable guarda o valor."""

    def __init__(self, pai, opcoes, variable=None, comando=None):
        super().__init__(pai, bg=T.CAMPO, padx=3, pady=3)
        self.var = variable or tk.StringVar(value=opcoes[0][0])
        self.comando = comando
        self.itens = {}
        for valor, texto in opcoes:
            l = tk.Label(self, text=texto, font=T.F_PEQUENA, padx=12, pady=5, cursor="hand2")
            l.pack(side="left", fill="x", expand=True)
            l.bind("<Button-1>", lambda e, v=valor: self._escolher(v))
            self.itens[valor] = l
        self.var.trace_add("write", lambda *a: self._redesenhar())
        self._redesenhar()

    def _escolher(self, v):
        if self._desligado:
            return
        self.var.set(v)
        if self.comando:
            self.comando(v)

    def _redesenhar(self):
        for v, l in self.itens.items():
            if not l.winfo_exists():
                return
            sel = v == self.var.get()
            if self._desligado:
                l.configure(bg=T.CAMPO, fg=T.APAGADO, cursor="arrow")
            else:
                l.configure(bg=T.DESTAQUE if sel else T.CAMPO, fg="#ffffff" if sel else T.SUAVE, cursor="hand2")


# ---------------------------------------------------------------------------
class Chip(tk.Canvas):
    """Etiqueta arredondada clicavel, com um ponto de cor opcional."""

    def __init__(self, pai, texto, comando=None, selecionado=False, cor_ponto=None, icone=None,
                 menu=None, dica=None, altura=30):
        self.fonte = tkfont.Font(font=T.F_PEQUENA)
        self.texto, self.comando, self.sel, self.cor_ponto, self.icone = texto, comando, selecionado, cor_ponto, icone
        w = self.fonte.measure(texto) + 26 + (16 if cor_ponto else 0) + (18 if icone else 0)
        super().__init__(pai, width=w, height=altura, bg=fundo_de(pai), highlightthickness=0, cursor="hand2")
        self._sobre = False
        self.bind("<Enter>", lambda e: self._mudar(True))
        self.bind("<Leave>", lambda e: self._mudar(False))
        self.bind("<Button-1>", lambda e: comando and comando())
        if menu:
            self.bind("<Button-3>", lambda e: menu(e))
        if dica:
            Dica(self, dica)
        self._redesenhar()

    def _mudar(self, sobre):
        self._sobre = sobre
        self._redesenhar()

    def selecionar(self, sim):
        if sim != self.sel:
            self.sel = sim
            self._redesenhar()

    def ponto(self, cor):
        self.cor_ponto = cor
        self.itemconfigure("ponto", fill=cor)

    def _redesenhar(self):
        self.delete("all")
        w, h = int(self.cget("width")), int(self.cget("height"))
        if self.sel:
            retangulo(self, 1, 1, w - 1, h - 1, h / 2, fill=T.DESTAQUE_FUNDO, outline=T.DESTAQUE)
        else:
            retangulo(self, 1, 1, w - 1, h - 1, h / 2, fill=T.CAMPO_2 if self._sobre else T.CAMPO, outline="")
        x = 13
        if self.cor_ponto:
            self.create_oval(x, h / 2 - 4, x + 8, h / 2 + 4, fill=self.cor_ponto, outline="", tags="ponto")
            x += 16
        if self.icone:
            self.create_text(x + 6, h / 2 + 1, text=self.icone, font=(T.F_ICONE, 10),
                             fill=T.TEXTO if self.sel else T.SUAVE)
            x += 18
        self.create_text(x, h / 2, text=self.texto, font=self.fonte, anchor="w",
                         fill=T.TEXTO if self.sel or self._sobre else T.SUAVE)


# ---------------------------------------------------------------------------
class Contador(_Estado, tk.Frame):
    """Numero com botoes - e +, e campo editavel. comando() e chamado a cada mudanca."""

    def __init__(self, pai, variable, de=0, ate=999, comando=None, largura=5):
        super().__init__(pai, bg=T.CAMPO, padx=2, pady=2)
        self.var, self.de, self.ate, self.comando = variable, de, ate, comando
        self.menos = tk.Label(self, text="", font=(T.F_ICONE, 9), bg=T.CAMPO, fg=T.SUAVE, padx=8, cursor="hand2")
        self.menos.pack(side="left", fill="y")
        self.ent = tk.Entry(self, textvariable=variable, width=largura, justify="center", bg=T.CAMPO, fg=T.TEXTO,
                            insertbackground=T.TEXTO, relief="flat", font=T.F_TEXTO, highlightthickness=0,
                            disabledbackground=T.CAMPO, disabledforeground=T.APAGADO)
        self.ent.pack(side="left", ipady=3)
        self.mais = tk.Label(self, text="", font=(T.F_ICONE, 9), bg=T.CAMPO, fg=T.SUAVE, padx=8, cursor="hand2")
        self.mais.pack(side="left", fill="y")
        self.menos.bind("<Button-1>", lambda e: self.passo(-1))
        self.mais.bind("<Button-1>", lambda e: self.passo(1))
        for ev in ("<Return>", "<FocusOut>"):
            self.ent.bind(ev, lambda e: self._confirmar())
        self.ent.bind("<MouseWheel>", lambda e: (self.passo(1 if e.delta > 0 else -1), "break")[1])

    def passo(self, d):
        if self._desligado:
            return
        try:
            v = int(self.var.get())
        except (tk.TclError, ValueError):
            v = self.de
        self.var.set(max(self.de, min(self.ate, v + d)))
        if self.comando:
            self.comando()

    def _confirmar(self):
        if self._desligado:
            return
        try:
            v = int(self.var.get())
        except (tk.TclError, ValueError):
            return
        self.var.set(max(self.de, min(self.ate, v)))
        if self.comando:
            self.comando()

    def _redesenhar(self):
        self.ent.configure(state="disabled" if self._desligado else "normal")
        for w in (self.menos, self.mais):
            w.configure(fg=T.APAGADO if self._desligado else T.SUAVE, cursor="arrow" if self._desligado else "hand2")


# ---------------------------------------------------------------------------
class Rolavel(tk.Frame):
    """Area com rolagem vertical; os filhos vao em .dentro."""

    def __init__(self, pai, altura=None, bg=None):
        bg = bg or fundo_de(pai)
        super().__init__(pai, bg=bg)
        from tkinter import ttk
        self.tela = tk.Canvas(self, bg=bg, highlightthickness=0, height=altura or 100)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.tela.configure(yscrollcommand=self._barra)
        self.tela.pack(side="left", fill="both", expand=True)
        self.dentro = tk.Frame(self.tela, bg=bg)
        jan = self.tela.create_window(0, 0, anchor="nw", window=self.dentro)
        self.dentro.bind("<Configure>", lambda e: self.tela.configure(scrollregion=self.tela.bbox("all")))
        self.tela.bind("<Configure>", lambda e: self.tela.itemconfigure(jan, width=e.width))
        raiz = self.winfo_toplevel()
        if not getattr(raiz, "_rolagem_instalada", False):     # um so roteador para a janela toda
            raiz._rolagem_instalada = True
            raiz.bind_all("<MouseWheel>", Rolavel._roteador, add="+")

    @staticmethod
    def _roteador(e):
        """Manda a roda do mouse para a area rolavel que esta sob o ponteiro."""
        try:
            w = e.widget.winfo_containing(e.x_root, e.y_root)
        except (AttributeError, KeyError, tk.TclError):
            return
        while w is not None:
            if isinstance(w, Rolavel):
                w._roda(e)
                return
            w = w.master

    def _barra(self, a, b):
        if float(a) <= 0.0 and float(b) >= 1.0:      # cabe tudo: some com a barra
            self.barra.pack_forget()
        elif not self.barra.winfo_ismapped():
            self.barra.pack(side="right", fill="y", before=self.tela)
        self.barra.set(a, b)

    def _roda(self, e):
        if self.barra.winfo_ismapped():
            self.tela.yview_scroll(-e.delta // 120, "units")

    def limpar(self):
        for w in self.dentro.winfo_children():
            w.destroy()
        self.tela.yview_moveto(0)


# ---------------------------------------------------------------------------
class ListaLinhas(Rolavel):
    """Lista de linhas selecionaveis (titulo, detalhe, ponto de cor). ao_escolher(indice)."""

    def __init__(self, pai, altura=200, ao_escolher=None, bg=None):
        super().__init__(pai, altura=altura, bg=bg)
        self.ao_escolher = ao_escolher
        self.linhas, self.sel = [], None
        self.dentro.configure(bg=fundo_de(self))

    def definir(self, itens):
        """itens: [{"titulo", "detalhe"?, "cor"?}]"""
        bg = fundo_de(self)
        for w in self.dentro.winfo_children():
            w.destroy()
        self.linhas, self.sel, self.itens = [], None, list(itens)
        for i, it in enumerate(itens):
            f = tk.Frame(self.dentro, bg=bg, padx=10, pady=6, cursor="hand2")
            f.pack(fill="x", pady=1)
            if it.get("cor"):
                c = tk.Canvas(f, width=10, height=10, bg=bg, highlightthickness=0)
                c.create_oval(1, 1, 9, 9, fill=it["cor"], outline="")
                c.pack(side="left", padx=(0, 9))
            txt = tk.Frame(f, bg=bg)
            txt.pack(side="left", fill="x", expand=True)
            a = tk.Label(txt, text=it["titulo"], bg=bg, fg=T.TEXTO, font=T.F_TEXTO, anchor="w")
            a.pack(fill="x")
            filhos = [f, txt, a] + ([c] if it.get("cor") else [])
            if it.get("detalhe"):
                b = tk.Label(txt, text=it["detalhe"], bg=bg, fg=T.SUAVE, font=T.F_PEQUENA, anchor="w")
                b.pack(fill="x")
                filhos.append(b)
            for w in filhos:
                w.bind("<Button-1>", lambda e, i=i: self._clique(i))
                w.bind("<Enter>", lambda e, i=i: self._pintar(i, sobre=True))
                w.bind("<Leave>", lambda e, i=i: self._pintar(i))
            self.linhas.append(filhos)

    def _clique(self, i):
        self.selecionar(i)
        if self.ao_escolher:
            self.ao_escolher(i)

    def selecionar(self, i):
        antigo, self.sel = self.sel, i
        if antigo is not None and antigo < len(self.linhas):
            self._pintar(antigo)
        if i is not None and i < len(self.linhas):
            self._pintar(i)

    def _pintar(self, i, sobre=False):
        bg = T.DESTAQUE_FUNDO if i == self.sel else (T.CAMPO if sobre else fundo_de(self))
        for w in self.linhas[i]:
            if w.winfo_exists():
                w.configure(bg=bg)

    def __len__(self):
        return len(self.linhas)


# ---------------------------------------------------------------------------
class Dica:
    """Texto que aparece ao parar o mouse sobre um componente."""

    def __init__(self, w, texto):
        self.w, self.texto, self.jan, self._apos = w, texto, None, None
        w.bind("<Enter>", self._agendar, add="+")
        w.bind("<Leave>", self._esconder, add="+")
        w.bind("<ButtonPress>", self._esconder, add="+")

    def _agendar(self, e):
        self._apos = self.w.after(550, self._mostrar)

    def _mostrar(self):
        if self.jan or not self.w.winfo_exists():
            return
        x, y = self.w.winfo_rootx() + 8, self.w.winfo_rooty() + self.w.winfo_height() + 6
        self.jan = tk.Toplevel(self.w)
        self.jan.wm_overrideredirect(True)
        self.jan.wm_geometry(f"+{x}+{y}")
        tk.Label(self.jan, text=self.texto, bg=T.CAMPO_2, fg=T.TEXTO, font=T.F_PEQUENA, padx=9, pady=5,
                 justify="left", wraplength=320).pack()

    def _esconder(self, e=None):
        if self._apos:
            self.w.after_cancel(self._apos)
            self._apos = None
        if self.jan:
            self.jan.destroy()
            self.jan = None


# ---------------------------------------------------------------------------
def cartao(pai, padx=16, pady=14, **kw):
    return tk.Frame(pai, bg=T.CARTAO, highlightthickness=1, highlightbackground=T.LINHA, padx=padx, pady=pady, **kw)


def secao(pai, texto):
    return tk.Label(pai, text=texto.upper(), bg=fundo_de(pai), fg=T.SUAVE, font=T.F_SECAO, anchor="w")


def rotulo(pai, texto="", suave=False, fonte=None, **kw):
    return tk.Label(pai, text=texto, bg=fundo_de(pai), fg=T.SUAVE if suave else T.TEXTO,
                    font=fonte or (T.F_PEQUENA if suave else T.F_TEXTO), anchor="w", justify="left", **kw)


def entrada(pai, variable, largura=24):
    return tk.Entry(pai, textvariable=variable, width=largura, bg=T.CAMPO, fg=T.TEXTO, insertbackground=T.TEXTO,
                    relief="flat", font=T.F_TEXTO, highlightthickness=1, highlightbackground=T.LINHA,
                    highlightcolor=T.DESTAQUE)


def aviso(pai, texto, cor=None, icone=None, largura=230):
    """Caixa de informacao com icone. largura: onde o texto quebra a linha, em pixels."""
    f = tk.Frame(pai, bg=T.CAMPO, padx=12, pady=9)
    tk.Label(f, text=icone or T.I["info"], font=(T.F_ICONE, 11), bg=T.CAMPO, fg=cor or T.SUAVE).pack(side="left", anchor="n")
    l = tk.Label(f, text=texto, bg=T.CAMPO, fg=T.SUAVE, font=T.F_PEQUENA, justify="left", anchor="w", wraplength=largura)
    l.pack(side="left", padx=(9, 0), fill="x", expand=True)
    f.rotulo = l
    return f


def icone(pai, glifo, tamanho=14, cor=None, **kw):
    return tk.Label(pai, text=glifo, font=(T.F_ICONE, tamanho), bg=fundo_de(pai), fg=cor or T.SUAVE, **kw)
