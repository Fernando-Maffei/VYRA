"""Perfis, grupos de sincronizacao e layouts, gravados em um unico arquivo JSON.

Um perfil guarda tudo o que define a iluminacao: os grupos (quem participa, qual
efeito, cores, velocidade, intensidade, direcao), o brilho geral, o layout da
mesa em uso e os ajustes da captura de tela.

Um grupo com "todos": true vale para tudo, menos o que esta em "excluidos". As
listas "membros" e "excluidos" aceitam a chave de um dispositivo inteiro ou o id
de uma peca (uma fan, por exemplo). Quando uma peca esta em mais de um grupo
ativo, vale o primeiro da lista: e assim que o ajuste individual passa na frente.
"""
import copy, json, os


def grupo_novo(nome="Todos", todos=True, **campos):
    g = {"nome": nome, "ativo": True, "todos": todos, "membros": [], "excluidos": [],
         "efeito": "Cor estática", "cores": [[255, 255, 255]], "velocidade": 50,
         "intensidade": 100, "direcao": 0, "escala": 100,
         "percurso": "sequencia"}        # "sequencia": uma peca apos a outra; "mesa": pela posicao
    g.update(campos)
    return g


def perfil_novo(*grupos, **campos):
    p = {"grupos": list(grupos) or [grupo_novo()], "brilho": 100, "ligado": True, "layout": "Mesa",
         "fps": 30, "suavizacao": 35, "saturacao": 130, "todos_monitores": False}
    p.update(campos)
    return p


def padrao():
    return {
        "perfil_atual": "Personalizado",
        "perfis": {
            "Gaming": perfil_novo(grupo_novo(efeito="Onda", velocidade=60,
                                             cores=[[255, 0, 80], [90, 0, 255], [0, 200, 255]])),
            "Trabalho": perfil_novo(grupo_novo(efeito="Cor estática", intensidade=40,
                                               cores=[[255, 214, 170]])),
            "Filme": perfil_novo(grupo_novo(efeito="Tela"), fps=15),
            "Personalizado": perfil_novo(grupo_novo(efeito="Arco-íris")),
        },
        "layouts": {"Mesa": {"pecas": {}, "ordem": []}},
        "tamanhos": {},                     # chave do dispositivo -> {zona: quantidade de LEDs}
        "manter_ao_fechar": True,           # ao fechar o estudio, o luz_servico assume a iluminacao
        "montagem": {},                     # chave -> {zona: {"tipo": "fan"|"fita", "fans": n, "por_fan": n}}
    }


class Loja:
    def __init__(self, caminho):
        self.caminho = caminho
        self.dados = padrao()
        try:
            with open(caminho, encoding="utf-8") as f:
                lido = json.load(f)
            if isinstance(lido, dict) and isinstance(lido.get("perfis"), dict) and lido["perfis"]:
                for chave, valor in padrao().items():
                    lido.setdefault(chave, valor)
                self.dados = lido
        except (OSError, ValueError):
            pass
        if self.dados["perfil_atual"] not in self.dados["perfis"]:
            self.dados["perfil_atual"] = next(iter(self.dados["perfis"]))
        for nome, lay in list(self.dados["layouts"].items()):   # formato antigo: um retangulo por dispositivo
            if not (isinstance(lay, dict) and isinstance(lay.get("pecas"), dict)
                    and isinstance(lay.get("ordem"), list)):
                self.dados["layouts"][nome] = {"pecas": {}, "ordem": []}
        for p in self.dados["perfis"].values():         # arquivos antigos ou editados a mao
            for chave, valor in perfil_novo().items():
                p.setdefault(chave, copy.deepcopy(valor))
            p["grupos"] = [dict(grupo_novo(), **g) for g in p["grupos"]] or [grupo_novo()]

    def salvar(self):
        tmp = self.caminho + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.caminho)
            return True
        except OSError:
            return False

    # ---- perfis ------------------------------------------------------------
    @property
    def nomes(self):
        return list(self.dados["perfis"])

    @property
    def atual(self):
        return self.dados["perfil_atual"]

    def perfil(self):
        return self.dados["perfis"][self.dados["perfil_atual"]]

    def trocar(self, nome):
        if nome in self.dados["perfis"]:
            self.dados["perfil_atual"] = nome

    def criar(self, nome, copiar_do_atual=True):
        base = copy.deepcopy(self.perfil()) if copiar_do_atual else perfil_novo()
        self.dados["perfis"][nome] = base
        self.dados["perfil_atual"] = nome

    def excluir(self, nome):
        if nome in self.dados["perfis"] and len(self.dados["perfis"]) > 1:
            del self.dados["perfis"][nome]
            if self.dados["perfil_atual"] == nome:
                self.dados["perfil_atual"] = next(iter(self.dados["perfis"]))

    # ---- layouts -----------------------------------------------------------
    def layout(self):
        return self.dados["layouts"].setdefault(self.perfil().get("layout", "Mesa"),
                                                {"pecas": {}, "ordem": []})

    def criar_layout(self, nome):
        self.dados["layouts"][nome] = copy.deepcopy(self.layout())
        self.perfil()["layout"] = nome

    def excluir_layout(self, nome):
        if nome in self.dados["layouts"] and len(self.dados["layouts"]) > 1:
            del self.dados["layouts"][nome]
            resto = next(iter(self.dados["layouts"]))
            for p in self.dados["perfis"].values():
                if p.get("layout") == nome:
                    p["layout"] = resto


def quer(grupo, peca):
    """Este grupo quer controlar esta peca? As listas aceitam o id da peca ou a chave do dispositivo."""
    if grupo.get("todos"):
        fora = grupo.get("excluidos", ())
        return peca.id not in fora and peca.dev not in fora
    dentro = grupo.get("membros", ())
    return peca.id in dentro or peca.dev in dentro


def membros(grupo, pecas):
    """Pecas (da lista dada) que este grupo quer controlar."""
    return [p for p in pecas if quer(grupo, p)]


def distribuir(grupos, pecas):
    """[(grupo, [pecas])]: cada peca fica com o primeiro grupo ativo que a inclui."""
    livres = {p.id for p in pecas}
    saida = []
    for g in grupos:
        if not g.get("ativo", True):
            continue
        minhas = [p for p in pecas if p.id in livres and quer(g, p)]
        livres -= {p.id for p in minhas}
        saida.append((g, minhas))
    return saida


def definir_membro(grupo, alvo, dentro, pecas):
    """Poe ou tira do grupo uma peca (alvo = id) ou um dispositivo inteiro (alvo = chave)."""
    lista = "excluidos" if grupo.get("todos") else "membros"
    atual = list(grupo.get(lista, ()))
    do_dev = [p for p in pecas if p.dev == alvo]
    if do_dev:                              # dispositivo inteiro: esquece as pecas avulsas dele
        ids = {p.id for p in do_dev} | {alvo}
        atual = [k for k in atual if k not in ids]
        if dentro != bool(grupo.get("todos")):
            atual.append(alvo)
    else:
        peca = next((p for p in pecas if p.id == alvo), None)
        if peca and peca.dev in atual:      # estava "o dispositivo todo": abre em pecas
            atual.remove(peca.dev)
            atual += [p.id for p in pecas if p.dev == peca.dev and p.id not in atual]
        atual = [k for k in atual if k != alvo]
        if dentro != bool(grupo.get("todos")):
            atual.append(alvo)
    grupo[lista] = atual
