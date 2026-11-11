"""VYRA - Unified Lighting. Painel completo: dispositivos, efeitos, montagem, tela e perfis.

Abra com dois cliques (ou: pythonw luz_estudio.pyw).

Os efeitos daqui sao calculados pelo PC, quadro a quadro. Ao fechar a janela, o
luz_servico (um processo sem janela) assume e mantem a iluminacao rodando; ao abrir
de novo, o estudio retoma o controle.

Tudo o que voce configura fica em luz_estudio.json, ao lado deste arquivo.
A aparencia (cores, fontes, icones e componentes) fica na pasta ui/.
"""
import ctypes, os, sys, threading, time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, messagebox, simpledialog

PASTA = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
sys.path.insert(0, PASTA)
import luz
from rgb import dispositivos as dsp, efeitos, layout, perfis, servico, tela
from rgb.motor import Motor
from ui import tema as T
from ui.tema import hexa
from ui.widgets import (Botao, Chip, Contador, Deslizador, Dica, Interruptor, ListaLinhas, Rolavel, Segmentado,
                        aviso, cartao, entrada, icone, retangulo, rotulo, secao)

ESTADOS = {dsp.CONECTADO: (T.OK, "Conectado"), dsp.SEM_LEDS: (T.ALERTA, "Sem LEDs configurados"),
           dsp.INCOMPATIVEL: (T.ERRO, "Não compatível"), dsp.DESCONECTADO: (T.NEUTRO, "Desconectado")}
ESCALA_MESA = 0.7
MAX_CORES = 8
PAGINAS = [("Dispositivos", "dispositivos", "Seus aparelhos com iluminação"),
           ("Efeitos", "efeitos", "Escolha o que acende e como"),
           ("Montagem", "montagem", "O que está ligado, onde fica e em que ordem"),
           ("Tela", "tela", "As cores da tela nos seus LEDs"),
           ("Ajuda", "ajuda", "Compatibilidade e dicas")]
P_DISP, P_EFEITOS, P_MONT, P_TELA, P_AJUDA = range(5)
TIPOS_CANAL = [("fan", "Fans / anéis"), ("fita", "Fita / barra"), ("vazio", "Nada ligado")]
_TELA_FALSA = [[(40 + k * 6, 60 + l * 20, 200 - k * 4) for k in range(32)] for l in range(6)]


class Estudio:
    def __init__(self, raiz, host="127.0.0.1", porta=6742, arquivo=None, ler_usb=True, usar_servico=True,
                 porta_servico=servico.PORTA_CONTROLE):
        self.raiz, self.host, self.porta = raiz, host, porta
        self.usar_servico, self.porta_servico = usar_servico, porta_servico
        if usar_servico:                    # o servico e o estudio nao podem mandar cores ao mesmo tempo
            servico.parar(porta_servico)
        self.loja = perfis.Loja(arquivo or os.path.join(PASTA, "luz_estudio.json"))
        # ler_usb=False (testes) tambem deixa de fora os controladores que mexem no hardware real
        self.ger = dsp.gerenciador_padrao(host, porta) if ler_usb else dsp.Gerenciador(dsp.BackendOpenRGB(host, porta))
        self.motor = Motor(self.ger, self.loja)
        self.versao_vista = -1
        self.sujo, self.carregando = False, False
        self.grupo_sel = 0
        self.mesa_sel, self.arrasto = None, None
        self.zona_sel, self.zonas_lista, self.ordem_ids = None, [], []
        self.rot_efeito, self.faixas, self.chips_pecas = {}, {}, {}
        self.pagina = P_DISP

        raiz.title("VYRA · Unified Lighting")
        raiz.minsize(1340, 800)
        raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        T.aplicar(raiz)
        raiz.columnconfigure(1, weight=1)
        raiz.rowconfigure(0, weight=1)
        self._lateral()
        principal = tk.Frame(raiz, bg=T.FUNDO)
        principal.grid(row=0, column=1, sticky="nsew")
        self._cabecalho(principal)
        self.conteudo = tk.Frame(principal, bg=T.FUNDO)
        self.conteudo.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        self.conteudo.rowconfigure(0, weight=1)
        self.conteudo.columnconfigure(0, weight=1)
        self.paginas = []
        for construir in (self._pag_dispositivos, self._pag_efeitos, self._pag_montagem, self._pag_tela,
                          self._pag_ajuda):
            f = tk.Frame(self.conteudo, bg=T.FUNDO)
            f.grid(row=0, column=0, sticky="nsew")
            construir(f)
            self.paginas.append(f)
        self.ir(P_DISP)

        self.carregar_perfil()
        if ler_usb:                         # lista o USB uma vez, fora da thread da interface
            threading.Thread(target=self._ler_usb, daemon=True).start()
        self.motor.start()
        self._apos = self.raiz.after(80, self.tick)

    def _ler_usb(self):
        self.ger.usb = dsp.usb_presentes()
        self.ger.atualizar()
        self.motor.versao += 1

    def pecas(self):
        """As pecas atuais (fans, fitas...), ja com lugar garantido no layout em uso."""
        ps = layout.pecas(self.ger.controlaveis(), self.loja.dados["montagem"])
        layout.completar(self.loja.layout(), ps)
        return ps

    def _menu(self, e, itens):
        m = tk.Menu(self.raiz, tearoff=0)
        for texto, comando in itens:
            m.add_command(label=texto, command=comando)
        m.tk_popup(e.x_root, e.y_root)

    # ======================================================================
    # barra lateral, cabecalho e perfis
    # ======================================================================
    def _lateral(self):
        lat = tk.Frame(self.raiz, bg=T.LATERAL, width=212)
        lat.grid(row=0, column=0, sticky="ns")
        lat.pack_propagate(False)
        logo = tk.Frame(lat, bg=T.LATERAL)
        logo.pack(fill="x", padx=20, pady=(22, 26))
        marca = os.path.join(PASTA, "assets", "vyra_40.png")
        try:                                # o logo, se a imagem existir; senao, so o nome
            self._img_logo = tk.PhotoImage(file=marca)
            tk.Label(logo, image=self._img_logo, bg=T.LATERAL).pack(side="left", padx=(0, 10))
        except tk.TclError:
            pass
        nomes = tk.Frame(logo, bg=T.LATERAL)
        nomes.pack(side="left")
        tk.Label(nomes, text="VYRA", font=T.F_LOGO, bg=T.LATERAL, fg=T.TEXTO).pack(anchor="w")
        tk.Label(nomes, text="Unified Lighting", font=T.F_PEQUENA, bg=T.LATERAL, fg=T.SUAVE).pack(anchor="w")
        try:                                # icone da janela e da barra de tarefas
            self._img_icone = tk.PhotoImage(file=os.path.join(PASTA, "assets", "vyra_64.png"))
            self.raiz.iconphoto(True, self._img_icone)
        except tk.TclError:
            pass

        self.nav = []
        for i, (nome, ic, _) in enumerate(PAGINAS):
            f = tk.Frame(lat, bg=T.LATERAL, cursor="hand2")
            f.pack(fill="x", padx=10, pady=1)
            barra = tk.Frame(f, bg=T.LATERAL, width=3)
            barra.pack(side="left", fill="y")
            a = tk.Label(f, text=T.I[ic], font=(T.F_ICONE, 13), bg=T.LATERAL, fg=T.SUAVE, padx=12, pady=9)
            a.pack(side="left")
            b = tk.Label(f, text=nome, font=T.F_TEXTO, bg=T.LATERAL, fg=T.SUAVE, anchor="w")
            b.pack(side="left", fill="x", expand=True)
            for w in (f, a, b):
                w.bind("<Button-1>", lambda e, i=i: self.ir(i))
                w.bind("<Enter>", lambda e, i=i: self._nav_cor(i, True))
                w.bind("<Leave>", lambda e, i=i: self._nav_cor(i, False))
            self.nav.append((f, barra, a, b))

        rodape = tk.Frame(lat, bg=T.LATERAL)
        rodape.pack(side="bottom", fill="x", padx=18, pady=18)
        st = tk.Frame(rodape, bg=T.CAMPO, padx=12, pady=10)
        st.pack(fill="x", pady=(0, 14))
        l = tk.Frame(st, bg=T.CAMPO)
        l.pack(fill="x")
        self.ponto_status = tk.Canvas(l, width=10, height=10, bg=T.CAMPO, highlightthickness=0)
        self.ponto_status.pack(side="left", padx=(0, 7))
        self.rot_status = tk.Label(l, bg=T.CAMPO, fg=T.TEXTO, font=T.F_PEQUENA, anchor="w", justify="left",
                                   wraplength=140)
        self.rot_status.pack(side="left", fill="x")
        self.rot_status2 = tk.Label(st, bg=T.CAMPO, fg=T.SUAVE, font=T.F_PEQUENA, anchor="w", justify="left",
                                    wraplength=160)
        self.rot_status2.pack(fill="x", pady=(4, 0))
        self.rodape = self.rot_status       # nome antigo (estado da conexao), usado pelos testes
        self.v_manter = tk.BooleanVar(value=bool(self.loja.dados.get("manter_ao_fechar", True)))
        k = Interruptor(rodape, "Manter a luz ao fechar", self.v_manter, self.alternar_manter, fonte=T.F_PEQUENA,
                        cor_texto=T.SUAVE)
        k.pack(anchor="w", pady=3)
        Dica(k, "Ao fechar esta janela, um processo leve sem janela continua mandando os efeitos.")
        self.v_inicio = tk.BooleanVar(value=self._inicio_automatico())
        self.ck_inicio = Interruptor(rodape, "Iniciar com o Windows", self.v_inicio, self.alternar_inicio,
                                     fonte=T.F_PEQUENA, cor_texto=T.SUAVE)
        self.ck_inicio.pack(anchor="w", pady=3)
        if not self.usar_servico:
            self.ck_inicio.state(["disabled"])

    def _nav_cor(self, i, sobre):
        f, barra, a, b = self.nav[i]
        sel = i == self.pagina
        bg = T.CAMPO if sel or sobre else T.LATERAL
        for w in (f, a, b):
            w.configure(bg=bg)
        barra.configure(bg=T.DESTAQUE if sel else bg)
        a.configure(fg=T.DESTAQUE if sel else (T.TEXTO if sobre else T.SUAVE))
        b.configure(fg=T.TEXTO if sel or sobre else T.SUAVE, font=T.F_FORTE if sel else T.F_TEXTO)

    def ir(self, i):
        self.pagina = i
        self.paginas[i].tkraise()
        for k in range(len(self.nav)):
            self._nav_cor(k, False)
        self.rot_titulo.configure(text=PAGINAS[i][0])
        self.rot_subtitulo.configure(text=PAGINAS[i][2])
        if i == P_MONT:
            self.montar_montagem()

    def _cabecalho(self, pai):
        c = tk.Frame(pai, bg=T.FUNDO)
        c.pack(fill="x", padx=24, pady=(20, 12))
        tit = tk.Frame(c, bg=T.FUNDO)
        tit.pack(side="left")
        self.rot_titulo = tk.Label(tit, font=T.F_TITULO, bg=T.FUNDO, fg=T.TEXTO, anchor="w")
        self.rot_titulo.pack(anchor="w")
        self.rot_subtitulo = tk.Label(tit, font=T.F_TEXTO, bg=T.FUNDO, fg=T.SUAVE, anchor="w")
        self.rot_subtitulo.pack(anchor="w")

        dir_ = tk.Frame(c, bg=T.FUNDO)
        dir_.pack(side="right")
        self.v_brilho = tk.DoubleVar()
        Deslizador(dir_, "Brilho geral", 0, 100, self.v_brilho, lambda v: self._global("brilho", v),
                   largura=150).pack(side="right", padx=(18, 0))
        self.v_ligado = tk.BooleanVar()
        Interruptor(dir_, "Luz", self.v_ligado, lambda: self._global("ligado", self.v_ligado.get())).pack(
            side="right", padx=(18, 0), pady=(14, 0))
        pf = tk.Frame(dir_, bg=T.FUNDO)
        pf.pack(side="right")
        secao(pf, "Perfil").pack(anchor="w", pady=(0, 4))
        self.q_perfis = tk.Frame(pf, bg=T.FUNDO)
        self.q_perfis.pack(anchor="w")

    def montar_perfis(self):
        for w in self.q_perfis.winfo_children():
            w.destroy()
        for nome in self.loja.nomes:
            Chip(self.q_perfis, nome, comando=lambda n=nome: self.trocar_perfil(n), selecionado=nome == self.loja.atual,
                 menu=lambda e, n=nome: self._menu(e, [(f"Excluir “{n}”", lambda: self._excluir_perfil_nome(n))]),
                 dica="Clique para usar · botão direito para excluir").pack(side="left", padx=(0, 6))
        Chip(self.q_perfis, "Novo", comando=self.novo_perfil, icone=T.I["mais"],
             dica="Cria um perfil copiando o atual").pack(side="left")

    def _excluir_perfil_nome(self, nome):
        if nome != self.loja.atual:
            self.loja.trocar(nome)
        self.excluir_perfil()

    def _inicio_automatico(self):
        try:
            return self.usar_servico and servico.inicio_automatico()
        except OSError:
            return False

    def alternar_manter(self):
        self.loja.dados["manter_ao_fechar"] = bool(self.v_manter.get())
        self.sujo = True

    def alternar_inicio(self):
        try:
            servico.inicio_automatico(bool(self.v_inicio.get()), self.loja.caminho)
        except OSError as e:
            messagebox.showerror("VYRA", f"Não foi possível alterar o início com o Windows:\n{e}",
                                 parent=self.raiz)
            self.v_inicio.set(self._inicio_automatico())

    def _global(self, campo, valor):
        if self.carregando:
            return
        self.loja.perfil()[campo] = valor
        self.sujo = True

    def carregar_perfil(self):
        """Leva o perfil atual da loja para todos os controles."""
        self.carregando = True
        p = self.loja.perfil()
        self.v_brilho.set(p["brilho"])
        self.v_ligado.set(p["ligado"])
        self.v_fps.set(p["fps"]); self.v_suave.set(p["suavizacao"]); self.v_sat.set(p["saturacao"])
        self.v_monitores.set(p["todos_monitores"])
        self.carregando = False
        self.montar_perfis()
        self.montar_layouts()
        self.grupo_sel = min(self.grupo_sel, len(p["grupos"]) - 1)
        self.montar_montagem()
        self.listar_grupos()
        self.montar_dispositivos()

    def trocar_perfil(self, nome):
        self.loja.trocar(nome)
        self.grupo_sel = next((i for i, g in enumerate(self.grupos()) if g["ativo"]), 0)
        self.sujo = True
        self.carregar_perfil()

    def novo_perfil(self, nome=None):
        nome = nome or simpledialog.askstring("Novo perfil", "Nome do perfil (copia o atual):", parent=self.raiz)
        if not nome or not nome.strip():
            return
        nome = nome.strip()
        if nome in self.loja.nomes:
            messagebox.showinfo("VYRA", "Já existe um perfil com esse nome.", parent=self.raiz)
            return
        self.loja.criar(nome)
        self.sujo = True
        self.carregar_perfil()

    def excluir_perfil(self, confirmar=True):
        if len(self.loja.nomes) < 2:
            return
        if confirmar and not messagebox.askyesno("VYRA", f"Excluir o perfil “{self.loja.atual}”?",
                                                 parent=self.raiz):
            return
        self.loja.excluir(self.loja.atual)
        self.sujo = True
        self.carregar_perfil()

    # ======================================================================
    # pagina Dispositivos
    # ======================================================================
    def _pag_dispositivos(self, f):
        topo = tk.Frame(f, bg=T.FUNDO)
        topo.pack(fill="x", pady=(0, 12))
        self.rot_resumo = rotulo(topo, suave=True, fonte=T.F_TEXTO)
        self.rot_resumo.pack(side="left")
        Botao(topo, "Sincronizar tudo", self.sincronizar_todos, "primario", T.I["sincronizar"],
              dica="O grupo selecionado em Efeitos passa a valer para todos os aparelhos").pack(side="right")
        Botao(topo, "Abrir OpenRGB", self.abrir_openrgb, "fantasma", T.I["abrir"],
              dica="Abre o OpenRGB como administrador (necessário para memória e placa-mãe)").pack(side="right", padx=6)
        Botao(topo, "Atualizar", self.atualizar, "fantasma", T.I["atualizar"]).pack(side="right")
        self.rol_disp = Rolavel(f)
        self.rol_disp.pack(fill="both", expand=True)
        self.q_disp = self.rol_disp.dentro
        self.q_disp.columnconfigure(0, weight=1, uniform="c")
        self.q_disp.columnconfigure(1, weight=1, uniform="c")

    def donos(self):
        """id da peca -> grupo que a controla agora."""
        return {p.id: g for g, pg in perfis.distribuir(self.grupos(), self.pecas()) for p in pg}

    def _texto_efeito(self, pecas, donos):
        gs = [donos.get(p.id) for p in pecas]
        if not any(gs):
            return "Fora da sincronização"
        if all(g is gs[0] for g in gs):
            return f"{gs[0]['efeito']}  ·  grupo “{gs[0]['nome']}”"
        return "Peças em grupos diferentes"

    def montar_dispositivos(self):
        for w in self.q_disp.winfo_children():
            w.destroy()
        self.rot_efeito, self.faixas, self.chips_pecas = {}, {}, {}
        ds = self.ger.dispositivos
        ok = sum(1 for d in ds if d.controlavel)
        atencao = len(ds) - ok
        self.rot_resumo.configure(text=(f"{ok} aparelho(s) com luz" + (f"  ·  {atencao} precisa(m) de atenção"
                                                                         if atencao else "")) if ds else "")
        if not ds:
            vazio = tk.Frame(self.q_disp, bg=T.FUNDO)
            vazio.grid(row=0, column=0, columnspan=2, pady=80)
            icone(vazio, T.I["dispositivos"], 34, T.APAGADO).pack()
            rotulo(vazio, "Nenhum aparelho encontrado ainda", fonte=T.F_NOME).pack(pady=(12, 4))
            rotulo(vazio, "Abra o OpenRGB como administrador com o SDK Server ligado.", suave=True,
                   fonte=T.F_TEXTO).pack()
            Botao(vazio, "Abrir OpenRGB", self.abrir_openrgb, "primario", T.I["abrir"]).pack(pady=16)
            return
        ps, donos = self.pecas(), self.donos()
        linha = 0
        for cat in dsp.CATEGORIAS:
            desta = [d for d in ds if d.categoria == cat]
            if not desta:
                continue
            secao(self.q_disp, cat).grid(row=linha, column=0, columnspan=2, sticky="w", pady=(14 if linha else 0, 8))
            linha += 1
            for k, d in enumerate(desta):
                c = self._cartao(d, [p for p in ps if p.dev == d.chave], donos)
                c.grid(row=linha + k // 2, column=k % 2, sticky="nsew", padx=(0, 12) if k % 2 == 0 else 0, pady=(0, 12))
            linha += (len(desta) + 1) // 2

    def _cartao(self, d, pecas, donos):
        cor, texto = ESTADOS[d.estado]
        c = cartao(self.q_disp)
        topo = tk.Frame(c, bg=T.CARTAO)
        topo.pack(fill="x")
        ic = tk.Canvas(topo, width=42, height=42, bg=T.CARTAO, highlightthickness=0)
        retangulo(ic, 0, 0, 42, 42, 10, fill=T.CAMPO, outline="")
        ic.create_text(21, 22, text=T.I.get(d.categoria, T.I["Outros"]), font=(T.F_ICONE, 16),
                       fill=T.TEXTO if d.controlavel else T.APAGADO)
        ic.pack(side="left", padx=(0, 12))
        nomes = tk.Frame(topo, bg=T.CARTAO)
        nomes.pack(side="left", fill="x", expand=True)
        rotulo(nomes, d.nome, fonte=T.F_NOME).pack(anchor="w", fill="x")
        sem_fio = d.backend is not None and d.backend is not self.ger.backend
        detalhe = "  ·  ".join(x for x in (d.fabricante, f"{d.n_leds} LEDs" if d.n_leds else "",
                                           f"{len(pecas)} peças" if len(pecas) > 1 else "",
                                           "sem fio direto" if sem_fio and d.controlavel else "") if x)
        rotulo(nomes, detalhe, suave=True).pack(anchor="w")
        pill = tk.Frame(topo, bg=T.CAMPO, padx=9, pady=3)
        pill.pack(side="right", anchor="n")
        pc = tk.Canvas(pill, width=8, height=8, bg=T.CAMPO, highlightthickness=0)
        pc.create_oval(0, 0, 8, 8, fill=cor, outline="")
        pc.pack(side="left", padx=(0, 6))
        tk.Label(pill, text=texto, bg=T.CAMPO, fg=T.TEXTO, font=T.F_PEQUENA).pack(side="left")

        if d.controlavel:
            faixa = tk.Canvas(c, height=10, bg=T.CARTAO, highlightthickness=0)
            faixa.pack(fill="x", pady=(14, 8))
            self.faixas[d.chave] = (faixa, d)
            rot = rotulo(c, self._texto_efeito(pecas, donos), suave=True)
            rot.pack(anchor="w")
            self.rot_efeito[d.chave] = (rot, pecas)
            if len(pecas) > 1:                  # cada fan/fita do aparelho, editavel por conta propria
                q = tk.Frame(c, bg=T.CARTAO)
                q.pack(fill="x", pady=(10, 0))
                for k, p in enumerate(pecas):
                    ch = Chip(q, p.curto, comando=lambda p=p: self.editar_luz(p.id, p.nome), cor_ponto=T.CAMPO_2,
                              menu=lambda e, p=p: self._menu(e, [("Identificar (piscar)", lambda: self.motor.identificar(p.id)),
                                                                  ("Editar a luz desta peça", lambda: self.editar_luz(p.id, p.nome))]),
                              dica=f"{p.nome} · {p.qtd} LEDs\nClique para editar · botão direito para identificar",
                              altura=26)
                    ch.grid(row=k // 4, column=k % 4, sticky="w", padx=(0, 6), pady=(0, 6))
                    self.chips_pecas[p.id] = (ch, p)
                    self.rot_efeito[p.id] = (None, [p])
            b = tk.Frame(c, bg=T.CARTAO)
            b.pack(fill="x", pady=(12, 0))
            Botao(b, "Editar luz", lambda: self.editar_luz(d.chave, d.nome), "primario", T.I["editar"],
                  altura=30).pack(side="right")
            if d.zonas_ajustaveis:
                Botao(b, "Montagem", lambda: self.abrir_montagem(d), "fantasma", T.I["montagem"],
                      altura=30).pack(side="right", padx=6)
            Botao(b, "Identificar", lambda: self.motor.identificar(d.chave), "fantasma", T.I["identificar"],
                  altura=30, dica="Pisca o aparelho em branco por um instante").pack(side="right")
        else:
            if d.motivo:
                rotulo(c, d.motivo, suave=True, wraplength=470).pack(anchor="w", fill="x", pady=(12, 0))
            if d.zonas_ajustaveis:
                b = tk.Frame(c, bg=T.CARTAO)
                b.pack(fill="x", pady=(10, 0))
                Botao(b, "Montagem", lambda: self.abrir_montagem(d), "secundario", T.I["montagem"],
                      altura=30).pack(side="right")
        return c

    def desenhar_faixas(self):
        """Cores atuais de cada aparelho e de cada peca, no painel de dispositivos."""
        q = self.motor.quadros
        for chave, (cv, d) in self.faixas.items():
            if not cv.winfo_exists():
                continue
            cores = q.get(chave)
            w = cv.winfo_width()
            cv.delete("all")
            if not cores or w < 20:
                retangulo(cv, 0, 1, w, 9, 4, fill=T.CAMPO, outline="")
                continue
            n = min(len(cores), max(1, w // 9))
            passo = w / n
            for k in range(n):
                cor = cores[int(k * len(cores) / n)]
                retangulo(cv, k * passo + 1, 1, (k + 1) * passo - 1, 9, 3, fill=hexa(cor), outline="")
        for pid, (ch, p) in self.chips_pecas.items():
            cores = q.get(p.dev)
            if cores and ch.winfo_exists():
                trecho = cores[p.inicio:p.inicio + p.qtd] or [(0, 0, 0)]
                media = [sum(c[i] for c in trecho) / len(trecho) for i in range(3)]
                ch.ponto(hexa(media) if max(media) > 8 else T.CAMPO_2)

    def atualizar(self):
        self.motor.relistar()
        threading.Thread(target=self._ler_usb, daemon=True).start()

    def abrir_openrgb(self):
        exe = luz.achar_openrgb(None)
        if not exe:
            messagebox.showinfo("VYRA", "Não achei o OpenRGB.exe. Instale-o por openrgb.org.", parent=self.raiz)
            return
        # "runas" faz o Windows pedir a confirmacao de administrador (UAC)
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, "--server --startminimized", None, 1)
        if r <= 32:
            messagebox.showinfo("VYRA", "O OpenRGB não foi aberto (pedido de administrador recusado?).",
                                parent=self.raiz)

    def definir_canais(self, d, valores):
        """Ajusta no equipamento a quantidade de LEDs dos canais e guarda o que foi pedido."""
        limites = {zn: lim for _, zn, _, lim in d.zonas_ajustaveis}
        valores = {zn: max(limites[zn][0], min(limites[zn][1], v)) for zn, v in valores.items() if zn in limites}
        if self.loja.dados["tamanhos"].get(d.chave) != valores:
            self.loja.dados["tamanhos"][d.chave] = valores
            self.sujo = True
        if all(valores.get(zn, qtd) == qtd for _, zn, qtd, _ in d.zonas_ajustaveis):
            return                          # o equipamento ja esta com essas quantidades
        try:
            self.ger.backend.redimensionar(d, valores)
        except (luz.Erro, OSError, ValueError) as e:
            messagebox.showerror("VYRA", f"Não foi possível ajustar os canais:\n{e}", parent=self.raiz)
            return
        self.ger.atualizar()
        self.motor._enviado.clear()
        self.motor.versao += 1

    # ======================================================================
    # pagina Efeitos
    # ======================================================================
    def _pag_efeitos(self, f):
        dir_ = cartao(f, padx=20, pady=18, width=380)
        dir_.pack(side="right", fill="y", padx=(20, 0))
        dir_.pack_propagate(False)
        esq = tk.Frame(f, bg=T.FUNDO)
        esq.pack(side="left", fill="both", expand=True)

        # ---- a quem se aplica
        secao(esq, "Aplicar em").pack(anchor="w")
        self.q_grupos = tk.Frame(esq, bg=T.FUNDO)
        self.q_grupos.pack(fill="x", pady=(6, 8))
        barra = tk.Frame(esq, bg=T.FUNDO)
        barra.pack(fill="x")
        self.v_nome, self.v_ativo, self.v_efeito = tk.StringVar(), tk.BooleanVar(), tk.StringVar()
        self.v_percurso = tk.StringVar(value="sequencia")
        rotulo(barra, "Nome", suave=True).pack(side="left", padx=(0, 8))
        ent = entrada(barra, self.v_nome, 22)
        ent.pack(side="left", ipady=4)
        Dica(ent, "Nome do grupo")
        self.v_nome.trace_add("write", lambda *a: self._grupo("nome", self.v_nome.get()))
        Interruptor(barra, "Ativo", self.v_ativo, lambda: self._grupo("ativo", self.v_ativo.get())).pack(
            side="left", padx=(16, 0))
        Botao(barra, "", lambda: self.mover_grupo(-1), "fantasma", T.I["subir"], altura=30,
              dica="Mais prioridade: este grupo passa na frente dos de baixo").pack(side="left", padx=(16, 0))
        Botao(barra, "", lambda: self.mover_grupo(1), "fantasma", T.I["descer"], altura=30,
              dica="Menos prioridade").pack(side="left")
        Botao(barra, "Usar em tudo", self.sincronizar_todos, "fantasma", T.I["sincronizar"], altura=30,
              dica="Este grupo passa a valer para todos os aparelhos; os outros grupos são desligados").pack(
            side="left", padx=(8, 0))
        Botao(barra, "", self.excluir_grupo, "perigo", T.I["excluir"], altura=30, dica="Excluir este grupo").pack(
            side="left")
        self.rot_aviso = tk.Label(esq, bg=T.FUNDO, fg=T.ALERTA, font=T.F_PEQUENA, anchor="w", justify="left",
                                  wraplength=720)
        self.rot_aviso.pack(fill="x", pady=(6, 0))

        # ---- previa ao vivo
        secao(esq, "Ao vivo").pack(anchor="w", pady=(14, 6))
        cv = cartao(esq, padx=14, pady=12)
        cv.pack(fill="x")
        self.cv_previa = tk.Canvas(cv, height=56, bg=T.CARTAO, highlightthickness=0)
        self.cv_previa.pack(fill="x")

        # ---- galeria
        secao(esq, "Efeitos prontos").pack(anchor="w", pady=(16, 6))
        self.cv_gal = tk.Canvas(esq, height=10, bg=T.FUNDO, highlightthickness=0)
        self.cv_gal.pack(fill="x")
        self._gal = []
        self._montar_galeria()

        # ---- todos os efeitos
        secao(esq, "Ou escolha o efeito").pack(anchor="w", pady=(14, 6))
        self.chips_efeito = {}
        nomes = list(efeitos.EFEITOS)
        for i in range(0, len(nomes), 7):          # linhas de 7, com o espacamento natural de cada etiqueta
            q = tk.Frame(esq, bg=T.FUNDO)
            q.pack(fill="x", pady=(0, 6))
            for nome in nomes[i:i + 7]:
                ch = Chip(q, nome, comando=lambda n=nome: self._escolher_efeito(n), dica=efeitos.EFEITOS[nome][4])
                ch.pack(side="left", padx=(0, 6))
                self.chips_efeito[nome] = ch
        self.rot_desc = rotulo(esq, suave=True, fonte=T.F_TEXTO)
        self.rot_desc.pack(anchor="w", pady=(4, 0))

        # ---- ajustes (coluna direita)
        secao(dir_, "Cores").pack(anchor="w")
        self.q_paleta = tk.Frame(dir_, bg=T.CARTAO)
        self.q_paleta.pack(fill="x", pady=(8, 16))
        secao(dir_, "Percurso").pack(anchor="w")
        self.seg_percurso = Segmentado(dir_, [("sequencia", "Em sequência"), ("mesa", "Pela posição")],
                                       self.v_percurso, lambda v: self._grupo("percurso", v))
        self.seg_percurso.pack(fill="x", pady=(8, 4))
        Dica(self.seg_percurso, "Em sequência: a luz passa de uma peça para a próxima, na ordem da Montagem.\n"
                                "Pela posição: segue a posição das peças na mesa, na direção escolhida.")
        self.escalas = {}
        for campo, texto, de, ate, suf in (("velocidade", "Velocidade", 0, 100, "%"),
                                           ("intensidade", "Intensidade", 0, 100, "%"),
                                           ("escala", "Tamanho", 10, 300, "%"),
                                           ("direcao", "Direção", 0, 360, "°")):
            s = Deslizador(dir_, texto, de, ate, comando=lambda v, c=campo: self._grupo(c, v), largura=330, sufixo=suf)
            s.pack(fill="x", pady=(12, 0))
            self.escalas[campo] = s
        secao(dir_, "Participantes").pack(anchor="w", pady=(20, 6))
        self.v_todos = tk.BooleanVar()
        Interruptor(dir_, "Todos os aparelhos", self.v_todos, self._alternar_todos).pack(anchor="w")
        rotulo(dir_, "Os desmarcados abaixo ficam de fora.", suave=True).pack(anchor="w", pady=(2, 6))
        self.rol_membros = Rolavel(dir_, altura=120, bg=T.CARTAO)
        self.rol_membros.pack(fill="both", expand=True)
        self.q_membros = self.rol_membros.dentro

    def _montar_galeria(self):
        cv, larg, alt, gap, por_linha = self.cv_gal, 162, 66, 10, 4
        linhas = -(-len(efeitos.PREDEFINICOES) // por_linha)
        cv.configure(height=linhas * (alt + gap), width=por_linha * (larg + gap))
        self._gal = []
        for i, p in enumerate(efeitos.PREDEFINICOES):
            x, y = (i % por_linha) * (larg + gap), (i // por_linha) * (alt + gap)
            m = f"g{i}"
            fundo = retangulo(cv, x, y, x + larg, y + alt, 10, fill=T.CARTAO, outline=T.LINHA, tags=m)
            pts = []
            for k in range(18):
                cx = x + 14 + k * (larg - 28) / 17
                pts.append(cv.create_oval(cx - 3.5, y + 18, cx + 3.5, y + 25, fill=T.CAMPO, outline="", tags=m))
            cv.create_text(x + 14, y + 47, text=p["nome"], anchor="w", fill=T.TEXTO, font=T.F_PEQUENA, tags=m)
            cv.tag_bind(m, "<Button-1>", lambda e, i=i: self.aplicar_predefinicao(i))
            cv.tag_bind(m, "<Enter>", lambda e, i=i: (cv.config(cursor="hand2"), self._gal_sobre(i, True)))
            cv.tag_bind(m, "<Leave>", lambda e, i=i: (cv.config(cursor=""), self._gal_sobre(i, False)))
            self._gal.append((fundo, pts))

    def _gal_sobre(self, i, sim):
        g = self.grupo()
        p = efeitos.PREDEFINICOES[i]
        sel = p["efeito"] == g["efeito"] and [list(c) for c in p["cores"]] == [list(c) for c in g["cores"]]
        self.cv_gal.itemconfigure(self._gal[i][0], fill=T.CAMPO if sim else T.CARTAO,
                                  outline=T.DESTAQUE if sel else T.LINHA, width=2 if sel else 1)

    def desenhar_galeria(self, t):
        for i, p in enumerate(efeitos.PREDEFINICOES):
            ctx = efeitos.Contexto(t, p["cores"], p["velocidade"], 0, p["escala"], tela=_TELA_FALSA)
            pts = [((k + 0.5) / 18, 0.5) for k in range(18)]
            for oid, cor in zip(self._gal[i][1], efeitos.quadro(p["efeito"], ctx, pts)):
                self.cv_gal.itemconfigure(oid, fill=hexa(cor) if max(cor) > 6 else T.CAMPO)

    def desenhar_previa_grupo(self):
        """As pecas que o grupo selecionado controla, com as cores reais do momento."""
        cv = self.cv_previa
        cv.delete("all")
        w = cv.winfo_width()
        g, ps = self.grupo(), self.pecas()
        minhas = next((pg for gg, pg in perfis.distribuir(self.grupos(), ps) if gg is g), [])
        minhas = layout.em_ordem(self.loja.layout(), minhas)
        if not minhas:
            cv.create_text(w / 2, 28, text="Este grupo não está controlando nada agora.", fill=T.APAGADO,
                           font=T.F_TEXTO)
            return
        q = self.motor.quadros
        gap = 12
        disponivel = w - gap * (len(minhas) - 1)
        total = sum(min(p.qtd, 40) for p in minhas)
        x = 0
        for p in minhas:
            n = min(p.qtd, 40)
            largura = max(18, disponivel * n / total)
            cores = (q.get(p.dev) or [])[p.inicio:p.inicio + p.qtd]
            passo = largura / n
            for k in range(n):
                cor = cores[int(k * len(cores) / n)] if cores else (0, 0, 0)
                retangulo(cv, x + k * passo + 0.5, 6, x + (k + 1) * passo - 1, 30, 3,
                          fill=hexa(cor) if max(cor) > 6 else T.CAMPO, outline="")
            if largura > 46:
                cv.create_text(x + largura / 2, 45, text=p.curto, fill=T.SUAVE, font=T.F_PEQUENA)
            x += largura + gap

    def aplicar_predefinicao(self, i):
        p, g = efeitos.PREDEFINICOES[i], self.grupo()
        g.update(efeito=p["efeito"], cores=[list(c) for c in p["cores"]], velocidade=p["velocidade"],
                 escala=p["escala"], percurso=p["percurso"], direcao=0, ativo=True)
        self.sujo = True
        self.carregar_grupo()
        self.rotular_efeitos()

    def _escolher_efeito(self, nome):
        self.v_efeito.set(nome)
        self._grupo("efeito", nome)
        self._marcar_efeito()

    def _marcar_efeito(self):
        g = self.grupo()
        for nome, ch in self.chips_efeito.items():
            ch.selecionar(nome == g["efeito"])
        for i in range(len(self._gal)):
            self._gal_sobre(i, False)

    def grupos(self):
        return self.loja.perfil()["grupos"]

    def grupo(self):
        gs = self.grupos()
        self.grupo_sel = max(0, min(self.grupo_sel, len(gs) - 1))
        return gs[self.grupo_sel]

    def _controle(self):
        """id do grupo -> quantas pecas ele controla de fato agora."""
        return {id(g): len(pg) for g, pg in perfis.distribuir(self.grupos(), self.pecas())}

    def linhas_grupos(self):
        """Texto de cada grupo como aparece nos botoes (usado tambem nos testes)."""
        controle = self._controle()
        return [f"{g['nome']}  ·  {controle.get(id(g), 0)}" for g in self.grupos()]

    def listar_grupos(self):
        for w in self.q_grupos.winfo_children():
            w.destroy()
        for i, (g, texto) in enumerate(zip(self.grupos(), self.linhas_grupos())):
            Chip(self.q_grupos, texto, comando=lambda i=i: self.selecionar_grupo(i), selecionado=i == self.grupo_sel,
                 cor_ponto=T.OK if g["ativo"] else T.NEUTRO,
                 dica=f"Efeito: {g['efeito']}. O número é quantas peças este grupo controla agora.").pack(
                side="left", padx=(0, 6))
        Chip(self.q_grupos, "Novo grupo", comando=self.novo_grupo, icone=T.I["mais"],
             dica="Um grupo novo começa vazio e acima dos outros").pack(side="left")
        self.carregar_grupo()

    def selecionar_grupo(self, indice):
        self.grupo_sel = indice
        self.listar_grupos()

    def carregar_grupo(self):
        self.carregando = True
        g = self.grupo()
        self.v_nome.set(g["nome"]); self.v_ativo.set(g["ativo"]); self.v_efeito.set(g["efeito"])
        self.v_todos.set(g["todos"])
        self.v_percurso.set(g.get("percurso", "sequencia"))
        for campo, s in self.escalas.items():
            s.var.set(g[campo])
        self.carregando = False
        self._sensibilidade()
        self._marcar_efeito()
        self.montar_paleta()
        self.montar_membros()
        self.avisar_grupo()

    def _sensibilidade(self):
        g = self.grupo()
        _, usa_paleta, usa_vel, usa_dir, desc = efeitos.EFEITOS[g["efeito"]]
        self.rot_desc.configure(text=desc)
        em_fila = g.get("percurso") != "mesa" and g["efeito"] != "Tela"
        for campo, liga in (("velocidade", usa_vel), ("direcao", usa_dir and not em_fila), ("escala", usa_dir)):
            self.escalas[campo].state(["!disabled"] if liga else ["disabled"])
        self.seg_percurso.state(["!disabled"] if usa_dir else ["disabled"])
        self.usa_paleta = usa_paleta

    def _grupo(self, campo, valor):
        if self.carregando:
            return
        g = self.grupo()
        g[campo] = valor
        self.sujo = True
        if campo in ("efeito", "percurso"):
            self._sensibilidade()
            self.montar_paleta()
            self._marcar_efeito()
        if campo in ("nome", "ativo", "efeito"):
            self.rotular_efeitos()

    def montar_paleta(self):
        for w in self.q_paleta.winfo_children():
            w.destroy()
        g = self.grupo()
        if not self.usa_paleta:
            rotulo(self.q_paleta, "Este efeito não usa cores escolhidas.", suave=True).pack(anchor="w")
            return
        for i, cor in enumerate(g["cores"]):
            c = tk.Canvas(self.q_paleta, width=34, height=34, bg=T.CARTAO, highlightthickness=0, cursor="hand2")
            retangulo(c, 1, 1, 33, 33, 9, fill=hexa(cor), outline=T.LINHA)
            c.pack(side="left", padx=(0, 6))
            c.bind("<Button-1>", lambda e, i=i: self.trocar_cor(i))
            c.bind("<Button-3>", lambda e, i=i: self._menu(e, [("Trocar a cor", lambda: self.trocar_cor(i)),
                                                                ("Remover", lambda: self.remover_cor(i))]))
            Dica(c, "Clique para trocar · botão direito para remover")
        if len(g["cores"]) < MAX_CORES:
            Botao(self.q_paleta, "", self.adicionar_cor, "secundario", T.I["mais"], altura=34,
                  dica="Adicionar uma cor").pack(side="left")

    def trocar_cor(self, i, cor=None):
        g = self.grupo()
        if cor is None:
            cor, _ = colorchooser.askcolor(color=hexa(g["cores"][i]), parent=self.raiz, title="Cor")
        if cor:
            g["cores"][i] = [int(v) for v in cor[:3]]
            self.sujo = True
            self.montar_paleta()
            self._marcar_efeito()

    def adicionar_cor(self, cor=None):
        g = self.grupo()
        if len(g["cores"]) < MAX_CORES:
            g["cores"] = g["cores"] + [list(cor or g["cores"][-1])]
            self.sujo = True
            self.montar_paleta()
            if cor is None:
                self.trocar_cor(len(g["cores"]) - 1)

    def remover_cor(self, i):
        g = self.grupo()
        if len(g["cores"]) > 1:
            g["cores"] = g["cores"][:i] + g["cores"][i + 1:]
            self.sujo = True
            self.montar_paleta()
            self._marcar_efeito()

    def montar_membros(self):
        """Uma chave por aparelho e, quando ele tem varias pecas, uma por peca."""
        self.rol_membros.limpar()
        q = self.q_membros
        self.vars_membros = {}
        g, ps = self.grupo(), self.pecas()
        for d in self.ger.controlaveis():
            minhas = [p for p in ps if p.dev == d.chave]
            if not minhas:
                continue
            dentro = [perfis.quer(g, p) for p in minhas]
            v = tk.BooleanVar(value=all(dentro))
            self.vars_membros[d.chave] = v
            Interruptor(q, d.nome, v, lambda c=d.chave: self.alternar_membro(c)).pack(anchor="w", pady=(6, 2))
            if len(minhas) > 1:
                sub = tk.Frame(q, bg=T.CARTAO)
                sub.pack(anchor="w", padx=(30, 0))
                for k, p in enumerate(minhas):
                    vp = tk.BooleanVar(value=dentro[k])
                    self.vars_membros[p.id] = vp
                    Interruptor(sub, p.curto, vp, lambda c=p.id: self.alternar_membro(c), fonte=T.F_PEQUENA,
                                cor_texto=T.SUAVE).grid(row=k // 2, column=k % 2, sticky="w", padx=(0, 14), pady=2)
        if not self.vars_membros:
            rotulo(q, "Nenhum aparelho controlável no momento.", suave=True).pack(anchor="w")

    def alternar_membro(self, alvo, valor=None):
        """alvo: chave de um dispositivo (todas as pecas dele) ou id de uma peca."""
        if valor is None:
            valor = self.vars_membros[alvo].get()
        perfis.definir_membro(self.grupo(), alvo, bool(valor), self.pecas())
        self.sujo = True
        self.montar_membros()
        self.rotular_efeitos()

    def _alternar_todos(self):
        g, ps = self.grupo(), self.pecas()
        dentro = {p.id for p in perfis.membros(g, ps)}
        g["todos"] = self.v_todos.get()
        if g["todos"]:
            g["excluidos"] = [p.id for p in ps if p.id not in dentro]
        else:
            g["membros"] = [p.id for p in ps if p.id in dentro]
        self.sujo = True
        self.montar_membros()
        self.rotular_efeitos()

    def avisar_grupo(self):
        """Explica quando o grupo selecionado nao esta controlando o que deveria."""
        g, ps = self.grupo(), self.pecas()
        quer = perfis.membros(g, ps)
        tem = next((pg for gg, pg in perfis.distribuir(self.grupos(), ps) if gg is g), [])
        if not g["ativo"]:
            texto = "Grupo desligado: não controla nada. Ligue a chave “Ativo”."
        elif not quer:
            texto = "Nenhum participante marcado: escolha os aparelhos no painel à direita."
        elif len(tem) < len(quer):
            acima = next((gg["nome"] for gg in self.grupos()[:self.grupo_sel]
                          if gg["ativo"] and perfis.membros(gg, quer)), "outro grupo")
            texto = (f"{len(quer) - len(tem)} de {len(quer)} peça(s) estão seguindo o grupo “{acima}”, que vem antes "
                     "deste. Use a seta para cima para este grupo passar na frente.")
        else:
            texto = ""
        self.rot_aviso.configure(text=texto)

    def novo_grupo(self, nome=None, **campos):
        g = perfis.grupo_novo(nome or f"Grupo {len(self.grupos()) + 1}", todos=False, **campos)
        self.grupos().insert(0, g)
        self.grupo_sel = 0
        self.sujo = True
        self.listar_grupos()
        self.rotular_efeitos()
        return g

    def excluir_grupo(self):
        gs = self.grupos()
        if len(gs) > 1:
            del gs[self.grupo_sel]
            self.grupo_sel = max(0, self.grupo_sel - 1)
            self.sujo = True
            self.listar_grupos()
            self.rotular_efeitos()

    def mover_grupo(self, passo):
        gs, i = self.grupos(), self.grupo_sel
        j = i + passo
        if 0 <= j < len(gs):
            gs[i], gs[j] = gs[j], gs[i]
            self.grupo_sel = j
            self.sujo = True
            self.listar_grupos()
            self.rotular_efeitos()

    def editar_luz(self, alvo, nome):
        """Ajuste individual de um dispositivo ou de uma peca: um grupo so dele, acima dos demais."""
        gs = self.grupos()
        proprio = next((i for i, g in enumerate(gs) if not g["todos"] and g["membros"] == [alvo]), None)
        if proprio is None:
            ps = self.pecas()
            alvos = {p.id for p in ps if p.id == alvo or p.dev == alvo}
            dono = next((g for g, pg in perfis.distribuir(gs, ps) if any(p.id in alvos for p in pg)), gs[0])
            copia = {k: ([list(c) for c in dono[k]] if k == "cores" else dono[k])
                     for k in ("efeito", "cores", "velocidade", "intensidade", "direcao", "escala", "percurso")}
            self.novo_grupo(nome, membros=[alvo], **copia)
        else:
            g = gs.pop(proprio)             # volta para o topo: senao um grupo "tudo" acima o encobre
            g["ativo"] = True
            gs.insert(0, g)
            self.grupo_sel = 0
            self.sujo = True
            self.listar_grupos()
            self.rotular_efeitos()
        self.ir(P_EFEITOS)

    def sincronizar_todos(self):
        """O grupo selecionado passa a valer para tudo; os outros grupos sao desativados."""
        g = self.grupo()
        for outro in self.grupos():
            outro["ativo"] = outro is g
        g["todos"], g["excluidos"] = True, []
        self.sujo = True
        self.listar_grupos()
        self.rotular_efeitos()

    def rotular_efeitos(self):
        """Atualiza o que depende de quem controla o que: cartoes, botoes dos grupos e aviso."""
        donos = self.donos()
        for chave, (rot, pecas) in self.rot_efeito.items():
            if rot is not None and rot.winfo_exists():
                rot.configure(text=self._texto_efeito(pecas, donos))
        textos = self.linhas_grupos()
        chips = [w for w in self.q_grupos.winfo_children() if isinstance(w, Chip)][:-1]
        if [c.texto for c in chips] != textos or len(chips) != len(self.grupos()):
            self.listar_grupos()
        else:
            for c, g in zip(chips, self.grupos()):
                c.ponto(T.OK if g["ativo"] else T.NEUTRO)
            self.avisar_grupo()

    # ======================================================================
    # pagina Montagem: o que esta ligado, onde fica e em que ordem
    # ======================================================================
    def _pag_montagem(self, f):
        # ---- coluna 1: o que esta ligado em cada canal
        c1 = cartao(f, padx=18, pady=16, width=330)
        c1.pack(side="left", fill="y", padx=(0, 20))
        c1.pack_propagate(False)
        secao(c1, "1 · O que está ligado").pack(anchor="w")
        self.lista_zonas = ListaLinhas(c1, altura=210, ao_escolher=lambda i: self.selecionar_zona(), bg=T.CARTAO)
        self.lista_zonas.pack(fill="x", pady=(8, 12))
        self.rot_zona = rotulo(c1, "Escolha um canal acima.", fonte=T.F_FORTE, wraplength=290)
        self.rot_zona.pack(anchor="w", pady=(0, 8))
        self.v_tipo, self.v_fans, self.v_por = tk.StringVar(value="fita"), tk.IntVar(value=1), tk.IntVar(value=0)
        self.v_espec = tk.BooleanVar()
        self.seg_tipo = Segmentado(c1, TIPOS_CANAL, self.v_tipo, lambda v: self.aplicar_zona())
        self.seg_tipo.pack(fill="x")
        self.ck_espec = Interruptor(c1, "Quantidade específica de LEDs", self.v_espec, self.aplicar_zona)
        self.ck_espec.pack(anchor="w", pady=(12, 8))
        g = tk.Frame(c1, bg=T.CARTAO)
        g.pack(fill="x")
        rotulo(g, "Quantas fans").grid(row=0, column=0, sticky="w", pady=4)
        self.sp_fans = Contador(g, self.v_fans, 1, 40, self.aplicar_zona)
        self.sp_fans.grid(row=0, column=1, sticky="e", pady=4)
        self.rot_por = rotulo(g, "LEDs por fan")
        self.rot_por.grid(row=1, column=0, sticky="w", pady=4)
        self.sp_por = Contador(g, self.v_por, 0, 1024, self.aplicar_zona)
        self.sp_por.grid(row=1, column=1, sticky="e", pady=4)
        g.columnconfigure(0, weight=1)
        self.rot_total = rotulo(c1, suave=True, wraplength=290)
        self.rot_total.pack(anchor="w", pady=(8, 10))
        self.v_calibrar = tk.BooleanVar(value=True)
        Interruptor(c1, "Mostrar no aparelho enquanto ajusto", self.v_calibrar, fonte=T.F_PEQUENA,
                    cor_texto=T.SUAVE).pack(anchor="w")
        Botao(c1, "Todos os canais com todos os LEDs", self.tudo_automatico, "fantasma", T.I["atualizar"],
              altura=30).pack(anchor="w", pady=(10, 0))
        aviso(c1, "Para a luz passar de uma fan para a outra, ligue a quantidade específica e informe quantas "
                  "fans e LEDs por fan. Está certo quando cada fan acende inteira de uma cor (vermelha, azul…) "
                  "e o último LED fica branco.", largura=235).pack(side="bottom", fill="x")

        # ---- coluna 2: mesa e ordem
        c2 = tk.Frame(f, bg=T.FUNDO)
        c2.pack(side="left", fill="both", expand=True)
        topo = tk.Frame(c2, bg=T.FUNDO)
        topo.pack(fill="x")
        secao(topo, "Mesa").pack(side="left", padx=(0, 12))
        self.q_layouts = tk.Frame(topo, bg=T.FUNDO)
        self.q_layouts.pack(side="left")
        Botao(topo, "Ordem pela posição", self.ordem_pela_posicao, "fantasma", T.I["ordenar"], altura=30,
              dica="Numera as peças da esquerda para a direita, de cima para baixo").pack(side="right")
        Botao(topo, "Organizar em fila", self.organizar, "fantasma", T.I["montagem"], altura=30,
              dica="Coloca as peças lado a lado, na ordem da sequência").pack(side="right")
        self.mesa = tk.Canvas(c2, width=int(layout.LARGURA * ESCALA_MESA), height=int(layout.ALTURA * ESCALA_MESA),
                              bg=T.MESA, highlightthickness=1, highlightbackground=T.LINHA)
        self.mesa.pack(anchor="w", pady=(10, 0))
        self.mesa.bind("<Button-1>", self._mesa_clique)
        self.mesa.bind("<B1-Motion>", self._mesa_arrasta)
        self.mesa.bind("<ButtonRelease-1>", lambda e: setattr(self, "arrasto", None))
        self.mesa.bind("<MouseWheel>", self._mesa_roda)
        Dica(self.mesa, "Arraste as peças. Roda do mouse gira; Shift + roda muda o tamanho.\n"
                        "No efeito “Tela”, cada LED copia a região da tela onde ele está aqui.")

        secao(c2, "2 · Ordem da sequência").pack(anchor="w", pady=(14, 6))
        self.cv_ordem = tk.Canvas(c2, height=40, bg=T.FUNDO, highlightthickness=0)
        self.cv_ordem.pack(fill="x")
        self.cv_ordem.bind("<Configure>", lambda e: self.desenhar_ordem())
        sel = cartao(c2, padx=14, pady=10)
        sel.pack(fill="x", pady=(10, 0))
        l1 = tk.Frame(sel, bg=T.CARTAO)
        l1.pack(fill="x")
        self.rot_peca = rotulo(l1, "Clique numa peça na mesa ou na fila.", suave=True, fonte=T.F_FORTE)
        self.rot_peca.pack(side="left")
        self.v_invertido = tk.BooleanVar()
        self.ck_invertido = Interruptor(l1, "Inverter sentido", self.v_invertido,
                                        lambda: self._mesa_campo("invertido", self.v_invertido.get()))
        self.ck_invertido.pack(side="right")
        self.bt_depois = Botao(l1, "Depois", lambda: self.mover_ordem(1), "secundario", T.I["depois"], altura=30,
                               dica="Esta peça passa a acender depois da seguinte")
        self.bt_depois.pack(side="right", padx=(6, 18))
        self.bt_antes = Botao(l1, "Antes", lambda: self.mover_ordem(-1), "secundario", T.I["antes"], altura=30,
                              dica="Esta peça passa a acender antes da anterior")
        self.bt_antes.pack(side="right")
        l2 = tk.Frame(sel, bg=T.CARTAO)
        l2.pack(fill="x", pady=(8, 0))
        self.mesa_vars = {}
        for campo, texto, de, ate, suf in (("w", "Tamanho na mesa", 20, 600, ""), ("rot", "Rotação", 0, 359, "°")):
            s = Deslizador(l2, texto, de, ate, comando=lambda v, c=campo: self._mesa_campo(c, v), largura=300,
                           sufixo=suf)
            s.pack(side="left", padx=(0, 30))
            self.mesa_vars[campo] = s.var
            setattr(self, f"sl_{campo}", s)
        self._selecao_peca()

    # ---- pecas e listas ------------------------------------------------------
    def _montagem_de(self, d, zi):
        """A montagem de uma zona, com os padroes para o que nunca foi configurado."""
        zn, _, qtd = d.zonas[zi]
        lo, hi = d.limites[zi]
        m = self.loja.dados["montagem"].get(d.chave, {}).get(zn)
        if m is None:                       # nunca configurado: tudo aceso, ou o numero antigo salvo
            antigo = self.loja.dados["tamanhos"].get(d.chave, {}).get(zn)
            especifico = lo != hi and antigo is not None and antigo != max(lo, min(hi, layout.AUTO_MAX))
            m = {"tipo": "fita", "especifico": especifico, "fans": 1, "por_fan": 0, "leds": antigo or qtd}
        return m

    def _descricao_zona(self, d, zi):
        qtd = d.zonas[zi][2]
        m = self._montagem_de(d, zi)
        if m.get("tipo") == "vazio" or not qtd:
            return "nada ligado"
        if m.get("tipo") == "fan" and m.get("especifico", True) and m.get("por_fan"):
            por = int(m["por_fan"])
            n = -(-qtd // por)
            return f"{n} fan{'s' if n > 1 else ''} × {por} = {qtd} LEDs"
        nome = "anel" if m.get("tipo") == "fan" else "fita"
        ajustavel = d.limites[zi][0] != d.limites[zi][1]
        return f"{nome}, {qtd} LEDs" + (" (todos)" if ajustavel and not m.get("especifico") else "")

    def montar_montagem(self):
        """Refaz a lista de canais e a fila da sequencia, mantendo o que estava selecionado."""
        self.zonas_lista = [(d, zi) for d in self.ger.dispositivos if d.indice is not None
                            for zi in range(len(d.zonas))]
        itens = []
        for d, zi in self.zonas_lista:
            zn, _, qtd = d.zonas[zi]
            itens.append({"titulo": d.nome if len(d.zonas) == 1 else f"{d.nome} · {zn}",
                          "detalhe": self._descricao_zona(d, zi),
                          "cor": T.OK if qtd else T.NEUTRO})
        self.lista_zonas.definir(itens)
        if self.zona_sel:
            i = next((i for i, (d, zi) in enumerate(self.zonas_lista)
                      if (d.chave, d.zonas[zi][0]) == self.zona_sel), None)
            if i is None:
                self.zona_sel = None
            else:
                self.lista_zonas.selecionar(i)
        ps = self.pecas()
        fila = layout.em_ordem(self.loja.layout(), ps)
        self.ordem_ids = [p.id for p in fila]
        if self.mesa_sel not in self.ordem_ids:
            self.mesa_sel = None
        self.desenhar_ordem()
        self._selecao_peca()

    def desenhar_ordem(self):
        """A fila da sequencia: uma etiqueta numerada por peca, com setas entre elas."""
        cv = self.cv_ordem
        cv.delete("all")
        lay = self.loja.layout()
        ps = {p.id: p for p in self.pecas()}
        largura = cv.winfo_width() if cv.winfo_width() > 50 else 780
        medida = tkfont.Font(font=T.F_PEQUENA)
        x = y = 0
        for k, pid in enumerate(self.ordem_ids):
            p = ps.get(pid)
            if not p:
                continue
            sel = pid == self.mesa_sel
            texto = p.curto + ("  ⟲" if lay["pecas"].get(pid, {}).get("invertido") else "")
            w = medida.measure(texto) + 46
            if x and x + w > largura:          # nao cabe: continua na linha de baixo
                x, y = 0, y + 40
            m = f"o{k}"
            retangulo(cv, x, y + 4, x + w, y + 36, 16, fill=T.DESTAQUE_FUNDO if sel else T.CAMPO,
                      outline=T.DESTAQUE if sel else "", tags=m)
            cv.create_oval(x + 7, y + 10, x + 27, y + 30, fill=T.DESTAQUE if sel else T.CAMPO_2, outline="", tags=m)
            cv.create_text(x + 17, y + 20, text=str(k + 1), fill="#ffffff" if sel else T.SUAVE, font=T.F_SECAO,
                           tags=m)
            cv.create_text(x + 34, y + 20, text=texto, anchor="w", fill=T.TEXTO if sel else T.SUAVE,
                           font=T.F_PEQUENA, tags=m)
            cv.tag_bind(m, "<Button-1>", lambda e, pid=pid: self.selecionar_na_mesa(pid))
            cv.tag_bind(m, "<Enter>", lambda e: cv.config(cursor="hand2"))
            cv.tag_bind(m, "<Leave>", lambda e: cv.config(cursor=""))
            x += w
            if k < len(self.ordem_ids) - 1:
                cv.create_text(x + 11, y + 20, text=T.I["depois"], font=(T.F_ICONE, 9), fill=T.APAGADO)
                x += 22
        altura = y + 40
        if int(cv.cget("height")) != altura:
            cv.configure(height=altura)

    def montar_layouts(self):
        for w in self.q_layouts.winfo_children():
            w.destroy()
        atual = self.loja.perfil().get("layout")
        for nome in self.loja.dados["layouts"]:
            Chip(self.q_layouts, nome, comando=lambda n=nome: self.trocar_layout(n), selecionado=nome == atual,
                 menu=lambda e, n=nome: self._menu(e, [(f"Excluir “{n}”", lambda: self._excluir_layout_nome(n))]),
                 dica="Cada layout guarda uma disposição da mesa e a ordem da sequência.\n"
                      "Botão direito para excluir.", altura=28).pack(side="left", padx=(0, 6))
        Chip(self.q_layouts, "Novo", comando=self.novo_layout, icone=T.I["mais"], altura=28).pack(side="left")

    # ---- coluna 1: montagem de um canal --------------------------------------
    def _zona(self):
        """(dispositivo, indice da zona) da selecao atual, ou (None, None)."""
        if not self.zona_sel:
            return None, None
        d = self.ger.por_chave(self.zona_sel[0])
        zi = next((i for i, z in enumerate(d.zonas) if z[0] == self.zona_sel[1]), None) if d else None
        return (d, zi) if zi is not None else (None, None)

    def selecionar_zona(self, chave=None, zona=None):
        if chave is None:
            i = self.lista_zonas.sel
            if i is None or i >= len(self.zonas_lista):
                return
            d, zi = self.zonas_lista[i]
            chave, zona = d.chave, d.zonas[zi][0]
        self.zona_sel = (chave, zona)
        d, zi = self._zona()
        if d is None:
            self.zona_sel = None
            return
        m = self._montagem_de(d, zi)
        qtd = d.zonas[zi][2]
        fan = m.get("tipo") == "fan"
        self.carregando = True
        self.v_tipo.set(m.get("tipo") if m.get("tipo") in layout.TIPOS else "fita")
        self.v_espec.set(bool(m.get("especifico")))
        self.v_fans.set(int(m.get("fans") or 1))
        self.v_por.set(int(m.get("por_fan") or 0) if fan else int(m.get("leds") or qtd))
        self.carregando = False
        self._campos_zona()
        i = next((i for i, (dd, z) in enumerate(self.zonas_lista) if dd.chave == chave and z == zi), None)
        if i is not None:
            self.lista_zonas.selecionar(i)

    def _campos_zona(self):
        """Liga e desliga os campos conforme o tipo, e mostra o total."""
        d, zi = self._zona()
        if d is None:
            return
        zona, qtd, (lo, hi) = d.zonas[zi][0], d.zonas[zi][2], d.limites[zi]
        ajustavel = lo != hi
        tipo = self.v_tipo.get()
        espec = bool(self.v_espec.get())
        self.rot_zona.configure(text=(d.nome if len(d.zonas) == 1 else f"{d.nome} · {zona}"))
        self.rot_por.configure(text="LEDs por fan" if tipo == "fan" else "LEDs")
        self.ck_espec.state(["!disabled"] if ajustavel and tipo != "vazio" else ["disabled"])
        self.sp_fans.state(["!disabled"] if tipo == "fan" and (espec or not ajustavel) else ["disabled"])
        self.sp_por.state(["!disabled"] if ajustavel and espec and tipo != "vazio" else ["disabled"])
        if not ajustavel:
            texto = f"Total: {qtd} LEDs (quantidade fixa pelo aparelho)."
        elif tipo == "vazio":
            texto = "Canal desligado."
        elif espec:
            texto = f"Total neste canal: {qtd} LEDs (o canal aceita até {hi})."
        else:
            texto = f"Todos os LEDs do canal ({qtd}), como uma peça só."
        self.rot_total.configure(text=texto)

    def aplicar_zona(self):
        """Grava a montagem do canal selecionado e ajusta a quantidade de LEDs no equipamento."""
        if self.carregando:
            return
        d, zi = self._zona()
        if d is None:
            return
        try:
            fans, por = max(1, int(self.v_fans.get())), max(0, int(self.v_por.get()))
        except (tk.TclError, ValueError):
            return
        zona, qtd, (lo, hi) = d.zonas[zi][0], d.zonas[zi][2], d.limites[zi]
        ajustavel = lo != hi
        tipo = self.v_tipo.get() if self.v_tipo.get() in layout.TIPOS else "fita"
        if not ajustavel:                   # zona fixa: so da para dizer a forma e repartir em fans
            tipo = "fita" if tipo == "vazio" else tipo
            m = {"tipo": tipo, "especifico": True, "fans": fans if tipo == "fan" else 1,
                 "por_fan": -(-qtd // fans) if tipo == "fan" else 0, "leds": qtd}
        else:
            espec = bool(self.v_espec.get()) and tipo != "vazio"
            antes = self._montagem_de(d, zi)
            mesmo = antes.get("tipo") == tipo and bool(antes.get("especifico"))
            if espec and tipo == "fan" and (not mesmo or por == 0):
                por = 16                    # ponto de partida comum; o usuario ajusta olhando a fan
                self.v_por.set(por)
            if espec and tipo == "fita" and (not mesmo or por == 0):
                por = qtd or layout.AUTO_MAX    # o campo passa a ser o total do canal
                self.v_por.set(por)
            m = {"tipo": tipo, "especifico": espec, "fans": fans if tipo == "fan" else 1,
                 "por_fan": por if tipo == "fan" else 0, "leds": por if tipo == "fita" else fans * por}
        self.loja.dados["montagem"].setdefault(d.chave, {})[zona] = m
        self.sujo = True
        if ajustavel:
            self.definir_canais(d, layout.quantidades(d, self.loja.dados["montagem"], self.loja.dados["tamanhos"]))
        self._campos_zona()
        self.montar_montagem()

    def tudo_automatico(self):
        """Volta todos os canais ajustaveis do equipamento selecionado para "todos os LEDs"."""
        d, _ = self._zona()
        if d is None or not d.zonas_ajustaveis:
            return
        mont = self.loja.dados["montagem"].setdefault(d.chave, {})
        for _, zn, _, _ in d.zonas_ajustaveis:
            tipo = mont.get(zn, {}).get("tipo", "fita")
            mont[zn] = {"tipo": "fita" if tipo == "vazio" else tipo, "especifico": False,
                        "fans": 1, "por_fan": 0, "leds": 0}
        self.sujo = True
        self.definir_canais(d, layout.quantidades(d, self.loja.dados["montagem"], self.loja.dados["tamanhos"]))
        self.selecionar_zona(*self.zona_sel)
        self.montar_montagem()

    def abrir_montagem(self, d):
        """Vem do cartao do dispositivo: abre a pagina ja no primeiro canal ajustavel."""
        self.ir(P_MONT)
        zonas = d.zonas_ajustaveis
        self.selecionar_zona(d.chave, zonas[0][1] if zonas else d.zonas[0][0])

    # ---- coluna 2: a mesa ----------------------------------------------------
    def _mesa_ponto(self, e):
        return e.x / ESCALA_MESA, e.y / ESCALA_MESA

    def _mesa_clique(self, e):
        x, y = self._mesa_ponto(e)
        lay = self.loja.layout()
        achado = next((p for p in reversed(self.pecas()) if layout.contem(lay["pecas"][p.id], x, y)), None)
        self.selecionar_na_mesa(achado.id if achado else None)
        if achado:
            c = lay["pecas"][achado.id]
            self.arrasto = (x - c["x"], y - c["y"])

    def selecionar_na_mesa(self, peca_id):
        self.mesa_sel = peca_id if peca_id in self.ordem_ids else None
        self.desenhar_ordem()
        self._selecao_peca()

    def _selecao_peca(self):
        """Mostra a peca selecionada na barra abaixo da fila e liga ou desliga os controles dela."""
        tem = self.mesa_sel is not None
        for w in (self.bt_antes, self.bt_depois, self.ck_invertido, self.sl_rot, self.sl_w):
            w.state(["!disabled"] if tem else ["disabled"])
        if not tem:
            self.rot_peca.configure(text="Clique numa peça na mesa ou na fila para ajustá-la.", fg=T.SUAVE)
            return
        p = next((p for p in self.pecas() if p.id == self.mesa_sel), None)
        k = self.ordem_ids.index(self.mesa_sel) + 1
        self.rot_peca.configure(text=f"{k}. {p.nome if p else ''}", fg=T.TEXTO)
        c = self.loja.layout()["pecas"][self.mesa_sel]
        self.carregando = True
        self.mesa_vars["w"].set(c["w"])
        self.mesa_vars["rot"].set(c.get("rot", 0))
        self.v_invertido.set(bool(c.get("invertido")))
        self.carregando = False

    def _mesa_arrasta(self, e):
        if not self.arrasto or not self.mesa_sel:
            return
        x, y = self._mesa_ponto(e)
        self.mover_na_mesa(self.mesa_sel, x - self.arrasto[0], y - self.arrasto[1])

    def mover_na_mesa(self, peca_id, x, y):
        c = self.loja.layout()["pecas"][peca_id]
        c["x"] = max(-c["w"] / 2, min(layout.LARGURA - c["w"] / 2, x))
        c["y"] = max(-c["h"] / 2, min(layout.ALTURA - c["h"] / 2, y))
        self.sujo = True

    def _escalar(self, c, fator):
        cx, cy = c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
        c["w"], c["h"] = max(20, min(1000, c["w"] * fator)), max(10, min(600, c["h"] * fator))
        c["x"], c["y"] = cx - c["w"] / 2, cy - c["h"] / 2

    def _mesa_roda(self, e):
        if not self.mesa_sel:
            return
        c = self.loja.layout()["pecas"][self.mesa_sel]
        passo = 1 if e.delta > 0 else -1
        if e.state & 0x0001:                # Shift: tamanho
            self._escalar(c, 1.06 if passo > 0 else 1 / 1.06)
        else:
            c["rot"] = (c.get("rot", 0) + 5 * passo) % 360
        self.sujo = True
        self._selecao_peca()

    def _mesa_campo(self, campo, valor):
        if self.carregando or not self.mesa_sel:
            return
        c = self.loja.layout()["pecas"][self.mesa_sel]
        if campo == "w":                    # "Tamanho" mantem a proporcao da peca
            self._escalar(c, valor / c["w"])
        else:
            c[campo] = valor
        self.sujo = True
        if campo == "invertido":
            self.desenhar_ordem()

    def desenhar_mesa(self):
        m, e = self.mesa, ESCALA_MESA
        m.delete("all")
        for gx in range(0, int(layout.LARGURA * e), 35):       # grade discreta
            for gy in range(0, int(layout.ALTURA * e), 35):
                m.create_rectangle(gx, gy, gx + 1, gy + 1, fill="#1b2029", outline="")
        ps = self.pecas()
        lay = self.loja.layout()
        fila = layout.em_ordem(lay, ps)
        quadros = self.motor.quadros
        centros = [((lay["pecas"][p.id]["x"] + lay["pecas"][p.id]["w"] / 2) * e,
                    (lay["pecas"][p.id]["y"] + lay["pecas"][p.id]["h"] / 2) * e) for p in fila]
        if len(centros) > 1:                # o caminho da sequencia
            m.create_line([v for c in centros for v in c], fill="#3a3466", width=2, dash=(5, 4),
                          arrow="last", arrowshape=(10, 12, 5))
        for k, p in enumerate(fila):
            c = lay["pecas"][p.id]
            sel = p.id == self.mesa_sel
            pts = [v * e for q in layout.cantos(c) for v in q]
            m.create_polygon(pts, fill="#151922", outline=T.DESTAQUE if sel else T.LINHA, width=2 if sel else 1)
            cores = quadros.get(p.dev)
            raio = 4 if p.qtd <= 30 else (3 if p.qtd <= 80 else 2)
            for i, (x, y) in enumerate(layout.posicoes(p, c)):
                led = p.inicio + i
                cor = hexa(cores[led]) if cores and led < len(cores) else T.CAMPO_2
                m.create_oval(x * e - raio, y * e - raio, x * e + raio, y * e + raio, fill=cor, outline="")
            cx, cy = centros[k]
            m.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, fill=T.DESTAQUE if sel else T.CAMPO, outline="")
            m.create_text(cx, cy, text=str(k + 1), fill="#ffffff" if sel else T.SUAVE, font=T.F_SECAO)
            m.create_text((pts[0] + pts[4]) / 2, min(pts[1::2]) - 9, text=p.curto,
                          fill=T.TEXTO if sel else T.SUAVE, font=T.F_PEQUENA)

    # ---- a ordem e os layouts -----------------------------------------------
    def mover_ordem(self, passo):
        if not self.mesa_sel:
            return
        self.pecas()
        ordem = self.loja.layout()["ordem"]
        visiveis = [i for i in ordem if i in self.ordem_ids]
        k = visiveis.index(self.mesa_sel)
        if not 0 <= k + passo < len(visiveis):
            return
        a, b = ordem.index(visiveis[k]), ordem.index(visiveis[k + passo])
        ordem[a], ordem[b] = ordem[b], ordem[a]
        self.sujo = True
        self.montar_montagem()

    def ordem_pela_posicao(self):
        layout.ordenar_pela_posicao(self.loja.layout(), self.pecas())
        self.sujo = True
        self.montar_montagem()

    def organizar(self):
        layout.organizar_em_fila(self.loja.layout(), self.pecas())
        self.sujo = True
        self._selecao_peca()

    def trocar_layout(self, nome):
        if nome in self.loja.dados["layouts"]:
            self.loja.perfil()["layout"] = nome
            self.sujo = True
            self.mesa_sel = None
            self.montar_layouts()
            self.montar_montagem()

    def novo_layout(self, nome=None):
        nome = nome or simpledialog.askstring("Novo layout", "Nome do layout (copia o atual):", parent=self.raiz)
        if not nome or not nome.strip() or nome.strip() in self.loja.dados["layouts"]:
            return
        self.loja.criar_layout(nome.strip())
        self.sujo = True
        self.montar_layouts()

    def _excluir_layout_nome(self, nome):
        self.loja.perfil()["layout"] = nome
        self.excluir_layout()

    def excluir_layout(self):
        self.loja.excluir_layout(self.loja.perfil()["layout"])
        self.sujo = True
        self.montar_layouts()
        self.montar_montagem()

    # ======================================================================
    # pagina Tela
    # ======================================================================
    def _pag_tela(self, f):
        esq = cartao(f, padx=20, pady=18, width=400)
        esq.pack(side="left", fill="y", padx=(0, 20))
        esq.pack_propagate(False)
        secao(esq, "Captura").pack(anchor="w")
        self.v_fps, self.v_suave, self.v_sat = tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        self.v_monitores = tk.BooleanVar()
        for campo, v, texto, de, ate, mostrar in (
                ("fps", self.v_fps, "Quadros por segundo", 5, 60, lambda x: f"{x} por segundo"),
                ("suavizacao", self.v_suave, "Suavização", 0, 95, None),
                ("saturacao", self.v_sat, "Vivacidade das cores", 100, 250, None)):
            Deslizador(esq, texto, de, ate, v, lambda x, c=campo: self._tela(c, x), largura=350,
                       mostrar=mostrar).pack(fill="x", pady=(14, 0))
        Interruptor(esq, "Capturar todos os monitores", self.v_monitores,
                    lambda: self._tela("todos_monitores", self.v_monitores.get())).pack(anchor="w", pady=(18, 0))
        rotulo(esq, "Desligado, captura só o monitor principal.", suave=True).pack(anchor="w", padx=(47, 0))
        Botao(esq, "Usar a Tela no grupo selecionado", self.usar_tela, "primario", T.I["tela"]).pack(
            anchor="w", pady=(20, 0))
        self.rot_tela_estado = rotulo(esq, suave=True, wraplength=350)
        self.rot_tela_estado.pack(anchor="w", pady=(12, 0))
        aviso(esq, "Os quadros por segundo valem para todos os efeitos deste perfil. Jogos em tela cheia "
                   "exclusiva podem vir pretos (use janela sem bordas); vídeo protegido, como Netflix, vem "
                   "preto; com HDR as cores saem lavadas. A imagem não é gravada nem enviada a lugar nenhum.",
              largura=300).pack(side="bottom", fill="x")
        dir_ = tk.Frame(f, bg=T.FUNDO)
        dir_.pack(side="left", anchor="n")
        secao(dir_, "O que os LEDs estão vendo").pack(anchor="w")
        self.cel = 18
        moldura = cartao(dir_, padx=10, pady=10)
        moldura.pack(pady=(8, 0))
        self.previa = tk.Canvas(moldura, width=32 * self.cel, height=18 * self.cel, bg=T.MESA, highlightthickness=0)
        self.previa.pack()
        self.celulas = [[self.previa.create_rectangle(k * self.cel, l * self.cel, (k + 1) * self.cel - 1,
                                                      (l + 1) * self.cel - 1, fill=T.MESA, outline="")
                         for k in range(32)] for l in range(18)]

    def _tela(self, campo, valor):
        if self.carregando:
            return
        self.loja.perfil()[campo] = valor
        self.sujo = True

    def usar_tela(self):
        self.v_efeito.set("Tela")
        self._grupo("efeito", "Tela")
        self.v_ativo.set(True)
        self._grupo("ativo", True)

    def desenhar_previa(self):
        grade = self.motor.grade
        if not grade:
            self.rot_tela_estado.configure(text="A captura está desligada: nenhum grupo ativo usa o efeito “Tela”.")
            return
        self.rot_tela_estado.configure(text=f"Captura ligada  ·  {self.motor.ms:.1f} ms por quadro")
        for l, linha in enumerate(grade):
            for k, cor in enumerate(linha):
                self.previa.itemconfigure(self.celulas[l][k], fill=hexa(cor))

    # ======================================================================
    # pagina Ajuda
    # ======================================================================
    def _pag_ajuda(self, f):
        self.rol_ajuda = Rolavel(f)
        self.rol_ajuda.pack(fill="both", expand=True)
        self.q_ajuda = self.rol_ajuda.dentro

    def escrever_compat(self):
        self.rol_ajuda.limpar()
        q = self.q_ajuda
        dicas = [("Como os aparelhos são controlados",
                  "A maioria passa pelo OpenRGB, que conhece o protocolo de cada fabricante. O teclado AULA "
                  "sem fio tem um controle próprio e funciona mesmo com o OpenRGB fechado."),
                 ("Abra o OpenRGB como administrador",
                  "Sem isso ele não consegue ler o barramento SMBus e deixa de encontrar memória RAM e "
                  "componentes da placa-mãe. Ele só procura aparelhos ao iniciar: depois de ligar ou trocar "
                  "um aparelho entre cabo e sem fio, saia pelo ícone da bandeja e abra de novo."),
                 ("Logitech G HUB",
                  "O G HUB e o OpenRGB não controlam o mesmo mouse ao mesmo tempo. Deixe os serviços "
                  "logi_lamparray_service e LGHUBUpdaterService parados para usar o mouse aqui."),
                 ("Bateria",
                  "Aparelhos sem fio recebem as cores o tempo todo; efeitos animados gastam mais bateria.")]
        grade = tk.Frame(q, bg=T.FUNDO)
        grade.pack(fill="x")
        grade.columnconfigure(0, weight=1, uniform="a")
        grade.columnconfigure(1, weight=1, uniform="a")
        for k, (titulo, texto) in enumerate(dicas):
            c = cartao(grade)
            c.grid(row=k // 2, column=k % 2, sticky="nsew", padx=(0, 12) if k % 2 == 0 else 0, pady=(0, 12))
            rotulo(c, titulo, fonte=T.F_FORTE).pack(anchor="w")
            rotulo(c, texto, suave=True, wraplength=470).pack(anchor="w", pady=(6, 0))
        secao(q, "Seus aparelhos").pack(anchor="w", pady=(10, 8))
        for d in self.ger.dispositivos:
            cor, estado = ESTADOS[d.estado]
            c = cartao(q, pady=11)
            c.pack(fill="x", pady=(0, 8))
            l = tk.Frame(c, bg=T.CARTAO)
            l.pack(fill="x")
            icone(l, T.I.get(d.categoria, T.I["Outros"]), 13, T.TEXTO).pack(side="left", padx=(0, 10))
            rotulo(l, d.nome, fonte=T.F_FORTE).pack(side="left")
            pc = tk.Canvas(l, width=8, height=8, bg=T.CARTAO, highlightthickness=0)
            pc.create_oval(0, 0, 8, 8, fill=cor, outline="")
            pc.pack(side="right")
            rotulo(l, estado, suave=True).pack(side="right", padx=(0, 6))
            via = "controle próprio" if d.backend is not None and d.backend is not self.ger.backend else "OpenRGB"
            rotulo(c, d.motivo or f"Controlado pelo {via}, {d.n_leds} LEDs.", suave=True,
                   wraplength=900).pack(anchor="w", pady=(4, 0), padx=(28, 0))

    # ======================================================================
    # ciclo da interface
    # ======================================================================
    def tick(self):
        m = self.motor
        if m.versao != self.versao_vista:
            self.versao_vista = m.versao
            self.montar_montagem()
            self.montar_dispositivos()
            self.montar_membros()
            self.rotular_efeitos()
            self.escrever_compat()
            if self.zona_sel:
                self.selecionar_zona(*self.zona_sel)
        p = self.pagina
        m.calibrando = self.zona_sel if p == P_MONT and self.v_calibrar.get() else None
        if p == P_DISP:
            self.desenhar_faixas()
        elif p == P_EFEITOS:
            self.desenhar_previa_grupo()
            self.desenhar_galeria(time.monotonic())
        elif p == P_MONT:
            self.desenhar_mesa()
        elif p == P_TELA:
            self.desenhar_previa()
        conectado = m.estado.startswith("OpenRGB conectado") or "sem fio" in m.estado
        self.ponto_status.delete("all")
        self.ponto_status.create_oval(1, 1, 9, 9, fill=T.OK if conectado else T.ALERTA, outline="")
        self.rot_status.configure(text=m.estado)
        self.rot_status2.configure(text=f"{m.fps_real:.0f} quadros/s  ·  {m.ms:.1f} ms" +
                                        (f"\nerro: {m.erro}" if m.erro else ""))
        if self.sujo and time.monotonic() - getattr(self, "_salvo_em", 0) > 2.0:
            self.salvar()
        self._apos = self.raiz.after(80, self.tick)

    def salvar(self):
        self.loja.salvar()
        self.sujo, self._salvo_em = False, time.monotonic()

    def fechar(self):
        self.raiz.after_cancel(self._apos)
        self.motor.calibrando = None
        self.salvar()
        self.motor.parar()
        if self.usar_servico and self.v_manter.get():   # o servico assume a iluminacao
            try:
                servico.iniciar(self.loja.caminho, self.host, self.porta, self.porta_servico)
            except OSError:
                pass
        self.raiz.destroy()


def main():
    import argparse
    p = argparse.ArgumentParser(prog="vyra")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=6742)
    a = p.parse_args()
    tela.tornar_ciente_de_dpi()
    raiz = tk.Tk()
    raiz.geometry("1400x860")
    Estudio(raiz, a.host, a.porta)
    raiz.mainloop()


if __name__ == "__main__":
    main()
