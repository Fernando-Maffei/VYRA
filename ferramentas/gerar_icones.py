"""Gera os icones do VYRA em assets/ (precisa de: pip install pillow; so para quem mexe no logo).

  python ferramentas/gerar_icones.py               # desenha o logo em vetor
  python ferramentas/gerar_icones.py logo.png      # usa uma imagem pronta (quadrada, fundo escuro)

Saidas: vyra_256.png (README), vyra_64.png (icone da janela), vyra_40.png (barra lateral)
e vyra.ico (atalho, varios tamanhos). O programa so le os PNG/ICO prontos; nao precisa do Pillow.
"""
import os, sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "assets")
LADO = 1024


def degrade(cores, lado=LADO):
    """Degrade horizontal passando pelas cores dadas."""
    im = Image.new("RGB", (lado, 1))
    n = len(cores) - 1
    for x in range(lado):
        f = x / (lado - 1) * n
        i = min(int(f), n - 1)
        a, b = cores[i], cores[i + 1]
        t = f - i
        im.putpixel((x, 0), tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    return im.resize((lado, lado))


def mascara(pontos):
    m = Image.new("L", (LADO, LADO), 0)
    ImageDraw.Draw(m).polygon(pontos, fill=255)
    return m


def desenhar():
    """O V do VYRA: dois bracos com degrade violeta -> azul -> ciano e um brilho em volta."""
    esq = [(205, 283), (368, 283), (488, 492), (470, 560), (505, 787)]       # braco esquerdo
    dir_ = [(645, 283), (807, 283), (505, 787), (455, 700)]                  # braco direito
    m_esq, m_dir = mascara(esq), mascara(dir_)
    cor_esq = degrade([(196, 40, 255), (122, 52, 255), (64, 60, 240)])
    cor_dir = degrade([(40, 70, 255), (24, 140, 255), (40, 235, 255)])
    v = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    v.paste(cor_esq, (0, 0), m_esq)
    v.paste(cor_dir, (0, 0), m_dir)
    # luz suave na borda de cima de cada braco
    luz = Image.new("L", (LADO, LADO), 0)
    d = ImageDraw.Draw(luz)
    d.line([(214, 289), (360, 289)], fill=200, width=5)
    d.line([(652, 289), (800, 289)], fill=220, width=5)
    luz = ImageChops.multiply(luz.filter(ImageFilter.GaussianBlur(3)), ImageChops.lighter(m_esq, m_dir))
    v = Image.composite(Image.new("RGBA", (LADO, LADO), (255, 255, 255, 255)), v, luz.point(lambda p: p // 3))
    # brilho
    forma = ImageChops.lighter(m_esq, m_dir)
    brilho = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    brilho.paste(degrade([(170, 60, 255), (60, 110, 255), (40, 220, 255)]), (0, 0), forma)
    brilho = brilho.filter(ImageFilter.GaussianBlur(26))
    a = brilho.getchannel("A").point(lambda p: int(p * 0.75))
    brilho.putalpha(a)
    final = Image.alpha_composite(brilho, v)
    return final.crop((150, 180, 860, 890))          # quadrado em volta do V, sem o fundo vazio


def de_arquivo(caminho):
    im = Image.open(caminho).convert("RGBA")
    w, h = im.size
    lado = min(w, h)
    return im.crop(((w - lado) // 2, (h - lado) // 2, (w + lado) // 2, (h + lado) // 2))


def main():
    os.makedirs(SAIDA, exist_ok=True)
    logo = de_arquivo(sys.argv[1]) if len(sys.argv) > 1 else desenhar()
    for lado in (256, 64, 40):
        logo.resize((lado, lado), Image.LANCZOS).save(os.path.join(SAIDA, f"vyra_{lado}.png"))
    logo.resize((256, 256), Image.LANCZOS).save(os.path.join(SAIDA, "vyra.ico"),
                                                 sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                        (256, 256)])
    print("icones gerados em", SAIDA)


if __name__ == "__main__":
    main()
