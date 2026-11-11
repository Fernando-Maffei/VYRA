"""Acesso a dispositivos HID pela hidapi que ja vem instalada com o OpenRGB (hidapi-hotplug.dll).

Usar a DLL do OpenRGB evita mais uma dependencia: quem usa este projeto ja precisa do
OpenRGB instalado. Outro caminho pode ser indicado pela variavel LUZ_HIDAPI.
"""
import ctypes, os
from ctypes import POINTER, Structure, c_char_p, c_int, c_size_t, c_ubyte, c_ushort, c_void_p, c_wchar_p

import luz


class _Info(Structure):
    pass


_Info._fields_ = [("path", c_char_p), ("vendor_id", c_ushort), ("product_id", c_ushort),
                  ("serial_number", c_wchar_p), ("release_number", c_ushort),
                  ("manufacturer_string", c_wchar_p), ("product_string", c_wchar_p),
                  ("usage_page", c_ushort), ("usage", c_ushort), ("interface_number", c_int),
                  ("next", POINTER(_Info))]

_dll = None


def _carregar():
    global _dll
    if _dll is not None:
        return _dll
    candidatos = [os.environ.get("LUZ_HIDAPI")]
    exe = luz.achar_openrgb(None)
    if exe:
        candidatos.append(os.path.join(os.path.dirname(exe), "hidapi-hotplug.dll"))
        candidatos.append(os.path.join(os.path.dirname(exe), "hidapi.dll"))
    for c in candidatos:
        if c and os.path.isfile(c):
            dll = ctypes.CDLL(c)
            dll.hid_enumerate.restype = POINTER(_Info)
            dll.hid_enumerate.argtypes = [c_ushort, c_ushort]
            dll.hid_free_enumeration.argtypes = [POINTER(_Info)]
            dll.hid_open_path.restype = c_void_p
            dll.hid_open_path.argtypes = [c_char_p]
            dll.hid_close.argtypes = [c_void_p]
            dll.hid_write.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t]
            dll.hid_read_timeout.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t, c_int]
            dll.hid_get_report_descriptor.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t]
            dll.hid_error.restype = c_wchar_p
            dll.hid_error.argtypes = [c_void_p]
            dll.hid_init()
            _dll = dll
            return dll
    raise OSError("hidapi nao encontrada (instale o OpenRGB ou indique LUZ_HIDAPI)")


def disponivel():
    try:
        _carregar()
        return True
    except OSError:
        return False


def listar(vid=0, pid=0):
    """Colecoes HID presentes: [{path, vid, pid, versao, pagina, uso, interface, produto}]."""
    dll = _carregar()
    saida, p = [], dll.hid_enumerate(vid, pid)
    cabeca = p
    while p:
        i = p.contents
        saida.append({"path": i.path, "vid": i.vendor_id, "pid": i.product_id, "versao": i.release_number,
                      "pagina": i.usage_page, "uso": i.usage, "interface": i.interface_number,
                      "produto": i.product_string or ""})
        p = i.next
    if cabeca:
        dll.hid_free_enumeration(cabeca)
    return saida


class Aberto:
    """Uma colecao HID aberta."""

    def __init__(self, path):
        self.dll = _carregar()
        self.h = self.dll.hid_open_path(path)
        if not self.h:
            raise OSError(f"nao abriu o dispositivo HID ({self.dll.hid_error(None)})")

    def descritor(self):
        buf = (c_ubyte * 4096)()
        n = self.dll.hid_get_report_descriptor(self.h, buf, 4096)
        return bytes(buf[:n]) if n > 0 else b""

    def escrever(self, dados):
        buf = (c_ubyte * len(dados))(*dados)
        n = self.dll.hid_write(self.h, buf, len(dados))
        if n != len(dados):
            raise OSError(f"falha ao escrever no HID ({self.dll.hid_error(self.h)})")

    def ler(self, tamanho=64, timeout_ms=250):
        """Bytes lidos, b"" se nada chegou no tempo, ou OSError."""
        buf = (c_ubyte * tamanho)()
        n = self.dll.hid_read_timeout(self.h, buf, tamanho, timeout_ms)
        if n < 0:
            raise OSError(f"falha ao ler do HID ({self.dll.hid_error(self.h)})")
        return bytes(buf[:n])

    def fechar(self):
        if self.h:
            self.dll.hid_close(self.h)
            self.h = None
