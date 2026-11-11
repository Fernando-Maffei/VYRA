"""luz servico - mantem a iluminacao rodando sem janela.

Normalmente quem inicia e encerra este programa e o luz_estudio (ao fechar e ao
abrir). Para rodar a mao: pythonw luz_servico.pyw
"""
import argparse, os, sys

PASTA = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
sys.path.insert(0, PASTA)
from rgb import servico, tela


def main():
    p = argparse.ArgumentParser(prog="luz_servico")
    p.add_argument("--arquivo", default=os.path.join(PASTA, "luz_estudio.json"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=6742)
    p.add_argument("--controle", type=int, default=servico.PORTA_CONTROLE)
    a = p.parse_args()
    tela.tornar_ciente_de_dpi()
    sys.exit(servico.executar(a.arquivo, a.host, a.porta, a.controle))


if __name__ == "__main__":
    main()
