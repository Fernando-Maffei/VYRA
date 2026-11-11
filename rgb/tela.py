"""Captura da tela reduzida a uma grade pequena de cores, para o efeito "Tela".

Usa so o que ja vem no Windows (GDI, via ctypes), em duas etapas: a tela e
amostrada para uma imagem intermediaria pequena e essa imagem e reduzida com
media (HALFTONE) para colunas x linhas, entao cada celula e a cor predominante
daquela regiao. Nada e gravado nem sai do computador.

Custo medido em 1920x1080: ~12 ms por captura, quase todo gasto pelo Windows
para entregar a imagem da tela; por isso o efeito "Tela" usa poucos quadros
por segundo. Baixar mais que isso exigiria a Desktop Duplication API (DXGI).

Limites conhecidos:
  - jogos em tela cheia exclusiva podem vir pretos (use "janela sem bordas");
  - video protegido (Netflix e similares) vem preto por causa do DRM;
  - com HDR ligado as cores chegam lavadas.
"""
import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
_gdi32.SetBrushOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
_gdi32.StretchBlt.argtypes = [wintypes.HDC] + [ctypes.c_int] * 4 + [wintypes.HDC] + [ctypes.c_int] * 4 + [wintypes.DWORD]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]

_COLORONCOLOR, _HALFTONE, _SRCCOPY = 3, 4, 0x00CC0020
_AMOSTRAS = 4           # a imagem intermediaria tem 4x4 amostras por celula da grade


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def tornar_ciente_de_dpi():
    """Sem isto, em telas com escala (125%, 150%) a captura pegaria so parte da tela."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            _user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class Captura:
    def __init__(self, colunas=32, linhas=18, todos_monitores=False):
        self.colunas, self.linhas, self.todos = colunas, linhas, todos_monitores
        self.hdc_tela = _user32.GetDC(None)
        self.mw, self.mh = colunas * _AMOSTRAS, linhas * _AMOSTRAS
        self.hdc_meio, self.bmp_meio, _, self.antigo_meio = self._superficie(self.mw, self.mh, _COLORONCOLOR)
        self.hdc_mem, self.bmp, self.bits, self.antigo = self._superficie(colunas, linhas, _HALFTONE)

    def _superficie(self, w, h, modo):
        hdc = _gdi32.CreateCompatibleDC(self.hdc_tela)
        cab = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bmp = _gdi32.CreateDIBSection(hdc, ctypes.byref(cab), 0, ctypes.byref(bits), None, 0)
        if not self.hdc_tela or not hdc or not bmp:
            raise OSError("nao foi possivel preparar a captura de tela")
        antigo = _gdi32.SelectObject(hdc, bmp)
        _gdi32.SetStretchBltMode(hdc, modo)
        _gdi32.SetBrushOrgEx(hdc, 0, 0, None)
        return hdc, bmp, bits, antigo

    def area(self):
        m = _user32.GetSystemMetrics
        if self.todos:
            return m(76), m(77), m(78), m(79)           # area virtual: todos os monitores
        return 0, 0, m(0), m(1)                         # monitor principal

    def capturar(self):
        """Devolve a grade [linha][coluna] de (r, g, b), ou None se a captura falhar."""
        x, y, w, h = self.area()
        if not _gdi32.StretchBlt(self.hdc_meio, 0, 0, self.mw, self.mh,
                                 self.hdc_tela, x, y, w, h, _SRCCOPY):
            return None
        if not _gdi32.StretchBlt(self.hdc_mem, 0, 0, self.colunas, self.linhas,
                                 self.hdc_meio, 0, 0, self.mw, self.mh, _SRCCOPY):
            return None
        bruto = ctypes.string_at(self.bits, self.colunas * self.linhas * 4)     # BGRA
        c = self.colunas
        return [[(bruto[4 * (l * c + k) + 2], bruto[4 * (l * c + k) + 1], bruto[4 * (l * c + k)])
                 for k in range(c)] for l in range(self.linhas)]

    def fechar(self):
        if self.hdc_mem:
            for hdc, bmp, antigo in ((self.hdc_mem, self.bmp, self.antigo),
                                     (self.hdc_meio, self.bmp_meio, self.antigo_meio)):
                _gdi32.SelectObject(hdc, antigo)
                _gdi32.DeleteObject(bmp)
                _gdi32.DeleteDC(hdc)
            _user32.ReleaseDC(None, self.hdc_tela)
            self.hdc_mem = None


def suavizar(anterior, nova, fator):
    """Mistura a grade nova na anterior. fator 1.0 = troca seca, perto de 0 = bem lento."""
    if anterior is None or fator >= 1.0:
        return nova
    return [[(a[0] + (n[0] - a[0]) * fator, a[1] + (n[1] - a[1]) * fator, a[2] + (n[2] - a[2]) * fator)
             for a, n in zip(la, ln)] for la, ln in zip(anterior, nova)]


def alguma_tecla():
    """True se alguma tecla ou botao do mouse esta pressionado agora (nao diz qual)."""
    estado = _user32.GetAsyncKeyState
    return any(estado(vk) & 0x8000 for vk in range(1, 255))
