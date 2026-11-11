"""Motor: calcula os quadros dos efeitos e envia aos dispositivos, em uma thread propria.

A cada passo: le o perfil atual, distribui os dispositivos entre os grupos,
calcula a cor de cada LED pela posicao dele na mesa e envia so o que mudou.
A captura de tela e a leitura de teclas so ficam ligadas enquanto algum grupo
ativo usa os efeitos "Tela" ou "Reativo".
"""
import math, threading, time

import luz
from . import efeitos, layout, tela
from .perfis import distribuir

REENVIO = 2.0           # reenvia um quadro parado a cada tantos segundos
RECONEXAO = 3.0         # intervalo entre tentativas de reconectar
REDESCOBERTA = (5.0, 30.0)  # apos conectar: relista a cada 5 s durante 30 s (o OpenRGB detecta aos poucos)


class Motor(threading.Thread):
    def __init__(self, gerenciador, loja):
        super().__init__(daemon=True, name="motor-rgb")
        self.ger, self.loja = gerenciador, loja
        self.rodando = True
        self.quadros = {}               # chave -> [(r, g, b)] do ultimo quadro (para a previa)
        self.grade = None               # ultima grade da tela (para a previa)
        self.versao = 0                 # sobe quando a lista de dispositivos muda
        self.estado = "Conectando ao OpenRGB..."
        self.fps_real, self.ms = 0.0, 0.0
        self.erro = ""
        self.identificando = {}         # chave -> instante em que a identificacao termina
        self.calibrando = None          # (chave, zona): canal em vermelho com o ultimo LED branco
        self._captura = None
        self._pulso, self._tecla = 0.0, False
        self._enviado = {}              # chave -> (cores, instante)
        self._versoes_extras = ()
        self._prox_conexao = 0.0
        self._conectou_em = None
        self._prox_lista = 0.0
        self._antes = time.monotonic()

    # ---- conexao e descoberta ----------------------------------------------
    def _conexao(self, agora):
        b = self.ger.backend
        if not b.conectado:
            if agora < self._prox_conexao:
                return
            self._prox_conexao = agora + RECONEXAO
            try:
                b.conectar()
            except (luz.Erro, OSError, ValueError):
                if any(d.backend is b for d in self.ger.dispositivos):
                    self._relistar()
                self.estado = "OpenRGB fechado ou sem o servidor (SDK Server) ligado"
                return
            self._conectou_em = agora
            self._prox_lista = agora + REDESCOBERTA[0]
            self._enviado.clear()
            self._relistar(aplicar_tamanhos=True)
        elif self._conectou_em is not None and agora >= self._prox_lista:
            if agora - self._conectou_em > REDESCOBERTA[1]:
                self._conectou_em = None
                return
            self._prox_lista = agora + REDESCOBERTA[0]
            antes = len(b.descobrir())
            try:
                b.conectar()
            except (luz.Erro, OSError, ValueError):
                return
            if len(b.descobrir()) != antes:
                self._relistar(aplicar_tamanhos=True)

    def _relistar(self, aplicar_tamanhos=False):
        self.ger.atualizar()
        if aplicar_tamanhos:                # canais ARGB voltam a 0 quando o OpenRGB reinicia
            mudou = False
            for d in self.ger.dispositivos:
                if d.zonas_ajustaveis:      # sem configuracao, o canal ja vem com todos os LEDs
                    quer = layout.quantidades(d, self.loja.dados["montagem"], self.loja.dados["tamanhos"])
                    try:
                        mudou |= self.ger.backend.redimensionar(d, quer)
                    except (luz.Erro, OSError, ValueError):
                        pass
            if mudou:
                self.ger.atualizar()
        n = len([d for d in self.ger.dispositivos if d.backend is self.ger.backend])
        extras = len([d for d in self.ger.dispositivos if d.backend is not self.ger.backend and d.controlavel])
        if self.ger.backend.conectado:
            self.estado = f"OpenRGB conectado - {n} dispositivo(s)"
        if extras:
            self.estado += f" + {extras} sem fio direto"
        self._enviado.clear()
        self.versao += 1

    def relistar(self):
        """Pedido da interface: refaz a conexao e a lista na proxima volta."""
        self.ger.backend.fechar()
        self._prox_conexao = 0.0

    def identificar(self, chave, segundos=1.5):
        """chave: a de um dispositivo inteiro ou o id de uma peca (uma fan)."""
        self.identificando[chave] = time.monotonic() + segundos

    # ---- um quadro -----------------------------------------------------------
    def passo(self, t):
        agora = time.monotonic()
        dt, self._antes = agora - self._antes, agora
        self._conexao(agora)
        versoes = tuple(e.versao for e in self.ger.extras)
        if versoes != self._versoes_extras:     # um controlador proprio achou ou perdeu um aparelho
            self._versoes_extras = versoes
            self._relistar()
        perfil = self.loja.perfil()
        lay = self.loja.layout()
        montagem = self.loja.dados["montagem"]
        ps = layout.pecas(self.ger.controlaveis(), montagem)
        layout.completar(lay, ps)
        partes = distribuir(perfil["grupos"], ps)
        usados = {g["efeito"] for g, pg in partes if pg}

        if "Tela" in usados and perfil.get("ligado", True):
            todos = bool(perfil.get("todos_monitores"))
            if self._captura is None or self._captura.todos != todos:
                if self._captura:
                    self._captura.fechar()
                self._captura = tela.Captura(todos_monitores=todos)
            nova = self._captura.capturar()
            if nova:
                fator = max(0.03, 1.0 - perfil.get("suavizacao", 35) / 100.0)
                self.grade = tela.suavizar(self.grade, nova, fator)
        elif self._captura:
            self._captura.fechar()
            self._captura, self.grade = None, None

        if "Reativo" in usados:
            apertada = tela.alguma_tecla()
            if apertada and not self._tecla:
                self._pulso = 1.0
            self._tecla = apertada
            self._pulso *= math.exp(-dt * 4.0)
        else:
            self._pulso = 0.0

        quadros = {}                        # chave do dispositivo -> (dispositivo, cores de todos os LEDs)

        def tela_de(chave):
            if chave not in quadros:
                d = self.ger.por_chave(chave)
                if not d:
                    return None
                quadros[chave] = (d, [(0, 0, 0)] * d.n_leds)
            return quadros[chave][1]

        brilho = perfil.get("brilho", 100) if perfil.get("ligado", True) else 0
        for g, pg in partes:
            if not pg:
                continue
            ctx = efeitos.Contexto(t, g["cores"], g["velocidade"], g["direcao"], g["escala"],
                                   tela=self.grade, pulso=self._pulso,
                                   saturacao=perfil.get("saturacao", 130) / 100.0)
            # "Tela" sempre usa a mesa: a mesa e a propria tela
            em_fila = g.get("percurso", "sequencia") != "mesa" and g["efeito"] != "Tela"
            fila = layout.pontos_sequencia(pg, lay) if em_fila else None
            for p in pg:
                destino = tela_de(p.dev)
                if destino is None:
                    continue
                pontos = fila[p.id] if em_fila else layout.pontos_mesa(p, lay)
                destino[p.inicio:p.inicio + p.qtd] = efeitos.quadro(
                    g["efeito"], ctx, pontos, g["intensidade"] * brilho / 100.0)[:len(destino) - p.inicio]
        for chave, ate in list(self.identificando.items()):
            alvos = [p for p in ps if p.id == chave or p.dev == chave]
            if agora >= ate or not alvos:
                del self.identificando[chave]
                continue
            cor = (255, 255, 255) if int(agora * 4) % 2 == 0 else (0, 0, 0)
            for p in alvos:
                destino = tela_de(p.dev)
                if destino is not None:
                    destino[p.inicio:p.inicio + p.qtd] = [cor] * min(p.qtd, len(destino) - p.inicio)

        cal = self.calibrando
        if cal:                             # ajuda a contar os LEDs de um canal (ver dialogo "LEDs por canal")
            d = self.ger.por_chave(cal[0])
            if d and d.n_leds:
                cores = [(0, 0, 12)] * d.n_leds
                m = montagem.get(d.chave, {}).get(cal[1], {})
                por = int(m.get("por_fan") or 0) if m.get("tipo") == "fan" and m.get("especifico", True) else 0
                for znome, inicio, qtd in d.zonas:
                    if znome == cal[1] and qtd:
                        for i in range(qtd):    # cada fan de uma cor: vermelha, azul, vermelha...
                            azul = por and (i // por) % 2
                            cores[inicio + i] = (0, 60, 255) if azul else (255, 0, 0)
                        cores[inicio + qtd - 1] = (255, 255, 255)
                quadros[d.chave] = (d, cores)

        for chave, (d, cores) in quadros.items():
            ultimo = self._enviado.get(chave)
            if ultimo and ultimo[0] == cores and agora - ultimo[1] < REENVIO:
                continue
            if self.ger.pintar(d, cores):
                self._enviado[chave] = (cores, agora)
        self.quadros = {k: v[1] for k, v in quadros.items()}

    def run(self):
        t0 = time.monotonic()
        while self.rodando:
            inicio = time.monotonic()
            try:
                self.passo(inicio - t0)
                self.erro = ""
            except Exception as e:          # o motor nunca pode morrer por causa de um quadro
                self.erro = f"{type(e).__name__}: {e}"
            gasto = time.monotonic() - inicio
            fps = max(1, min(60, int(self.loja.perfil().get("fps", 30))))
            time.sleep(max(0.002, 1.0 / fps - gasto))
            total = time.monotonic() - inicio
            self.ms += (gasto * 1000 - self.ms) * 0.1
            self.fps_real += (1.0 / total - self.fps_real) * 0.1

    def parar(self, apagar=False):
        self.rodando = False
        if self.is_alive():
            self.join(2.0)
        if self._captura:
            self._captura.fechar()
            self._captura = None
        if apagar:
            for d in self.ger.controlaveis():
                self.ger.pintar(d, [(0, 0, 0)] * d.n_leds)
        self.ger.fechar()
