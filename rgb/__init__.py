"""Nucleo do VYRA: efeitos por software, mesa (canvas), grupos e perfis.

Camadas (cada arquivo conhece apenas as de baixo):
  dispositivos.py  descoberta + comunicacao (hoje: OpenRGB; outros backends entram aqui)
  layout.py        onde cada LED fica na mesa
  efeitos.py       efeitos puros: (tempo, posicao) -> cor, sem saber de fabricante
  tela.py          captura da tela para o efeito "Tela"
  motor.py         laco que calcula os quadros e envia aos dispositivos
  perfis.py        perfis, grupos e layouts gravados em luz_estudio.json
"""
