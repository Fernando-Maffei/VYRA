"""Servico de iluminacao: um processo sem janela que so mantem os efeitos rodando.

O estudio e o editor; este servico e quem deixa as luzes funcionando com o
estudio fechado. Ele le o mesmo luz_estudio.json e relê quando o arquivo muda.

Nao e um "servico do Windows" de verdade, de proposito: aqueles rodam fora da
sessao do usuario, onde nao existe tela para capturar nem teclado para o efeito
Reativo, e exigem administrador para instalar. Este roda como um programa comum
em segundo plano e pode ser iniciado junto com o Windows (chave Run do usuario).

Controle por uma porta local (so 127.0.0.1): "estado" e "parar". A mesma porta
garante que exista um servico so.
"""
import json, os, socket, subprocess, sys, threading, time

from . import dispositivos, perfis
from .motor import Motor

PORTA_CONTROLE = 6741
_NOME_RUN = "LuzIluminacao"
_CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pedir(comando, porta=PORTA_CONTROLE, timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout) as s:
            s.sendall(comando.encode() + b"\n")
            s.settimeout(timeout)
            return s.recv(4096).decode("utf-8", "replace")
    except OSError:
        return None


def estado(porta=PORTA_CONTROLE):
    """Dicionario com o estado do servico, ou None se ele nao estiver rodando."""
    r = _pedir("estado", porta)
    try:
        return json.loads(r) if r else None
    except ValueError:
        return None


def parar(porta=PORTA_CONTROLE, espera=5.0):
    """Pede para o servico encerrar e espera ele sair. True se nao ha mais servico."""
    if _pedir("parar", porta) is None:
        return True
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        if _pedir("estado", porta, 0.2) is None:
            return True
        time.sleep(0.1)
    return False


def _comando(arquivo, host, porta_rgb, porta_controle):
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(exe):
        exe = sys.executable
    return [exe, os.path.join(PASTA, "luz_servico.pyw"), "--arquivo", arquivo, "--host", host,
            "--porta", str(porta_rgb), "--controle", str(porta_controle)]


def iniciar(arquivo, host="127.0.0.1", porta_rgb=6742, porta_controle=PORTA_CONTROLE):
    """Sobe o servico em segundo plano, solto do processo atual."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(_comando(arquivo, host, porta_rgb, porta_controle), cwd=PASTA,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=flags, close_fds=True)


def inicio_automatico(ligar=None, arquivo=None):
    """Consulta (ligar=None) ou altera o inicio junto com o Windows, so para o usuario atual."""
    import winreg
    if ligar is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN) as k:
                winreg.QueryValueEx(k, _NOME_RUN)
            return True
        except OSError:
            return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            cmd = _comando(arquivo or os.path.join(PASTA, "luz_estudio.json"), "127.0.0.1", 6742, PORTA_CONTROLE)
            winreg.SetValueEx(k, _NOME_RUN, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
        else:
            try:
                winreg.DeleteValue(k, _NOME_RUN)
            except OSError:
                pass
    return ligar


def executar(arquivo, host="127.0.0.1", porta_rgb=6742, porta_controle=PORTA_CONTROLE):
    """Laco do servico. Devolve 0 ao encerrar normalmente, 1 se ja havia outro rodando."""
    try:
        srv = socket.socket()
        srv.bind(("127.0.0.1", porta_controle))
        srv.listen(4)
    except OSError:
        return 1                            # a porta ocupada e o sinal de que ja existe um servico
    sair = threading.Event()
    loja = perfis.Loja(arquivo)
    motor = Motor(dispositivos.gerenciador_padrao(host, porta_rgb), loja)

    def atender():
        while not sair.is_set():
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                try:
                    c.settimeout(1.0)
                    pedido = c.recv(64).decode("utf-8", "replace").strip()
                    if pedido == "parar":
                        c.sendall(b"ok\n")
                        sair.set()
                    else:
                        c.sendall(json.dumps({
                            "pid": os.getpid(), "estado": motor.estado, "perfil": motor.loja.atual,
                            "qps": round(motor.fps_real, 1), "ms": round(motor.ms, 2),
                            "erro": motor.erro}).encode() + b"\n")
                except OSError:
                    pass

    threading.Thread(target=atender, daemon=True).start()
    motor.start()

    def carimbo():
        try:
            return os.path.getmtime(arquivo)
        except OSError:
            return 0
    visto = carimbo()
    while not sair.wait(1.0):
        agora = carimbo()
        if agora != visto:                  # o estudio (ou voce) gravou o arquivo: troca a configuracao
            visto = agora
            motor.loja = perfis.Loja(arquivo)
            motor._enviado.clear()
    motor.parar()
    srv.close()
    return 0
