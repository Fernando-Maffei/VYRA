"""Servidor OpenRGB de mentira, para testar o luz sem hardware.

Monta as respostas com o empacotador da biblioteca openrgb-python
(pip install openrgb-python) e imprime cada quadro de LEDs recebido.
Uso: python3 mock_server.py [porta] [versao_do_protocolo]
"""
import socket, struct, sys, threading
from openrgb import utils as u

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6742
SERVER_PROTO = int(sys.argv[2]) if len(sys.argv) > 2 else 4

def mode(i, name):
    return u.ModeData(i, name, i, u.ModeFlags.HAS_PER_LED_COLOR, None, None, None, None,
                      None, None, None, None, None, u.ModeColors.PER_LED, None)

def device(name, zones):
    zs, leds = [], []
    for zname, n, mat in zones:
        if mat == "ajustavel":  # canal ARGB: o cliente diz quantos LEDs tem
            zs.append(u.ZoneData(zname, u.ZoneType.LINEAR, 0, 120, n, 0, 0, None, []))
        elif mat:
            h, w = mat
            zs.append(u.ZoneData(zname, u.ZoneType.MATRIX, n, n, n, h, w,
                                 [[y * w + x for x in range(w)] for y in range(h)], []))
        else:
            zs.append(u.ZoneData(zname, u.ZoneType.LINEAR, n, n, n, 0, 0, None, []))
        leds += [u.LEDData(f"{zname} {i}", i) for i in range(n)]
    modes = [mode(0, "Direct"), mode(1, "Static")]
    modes[1].flags = u.ModeFlags.HAS_MODE_SPECIFIC_COLOR
    modes[1].color_mode = u.ModeColors.MODE_SPECIFIC
    modes[1].colors = [u.RGBColor(1, 2, 3)]
    modes[1].colors_min = modes[1].colors_max = 1
    # modo animado que roda no proprio dispositivo, com velocidade e brilho
    modes.append(u.ModeData(2, "Rainbow", 2, u.ModeFlags.HAS_SPEED | u.ModeFlags.HAS_BRIGHTNESS,
                            1, 10, 0, 100, None, None, 5, 100, None, u.ModeColors.NONE, None))
    return u.ControllerData(name, u.MetaData("ACME", "desc", "1.0", "SN", "HID: x"),
                            u.DeviceType.LEDSTRIP, leds, zs, modes,
                            [u.RGBColor(0, 0, 0)] * len(leds), 0)

def pack_zone(self, version):
    # O pack da biblioteca alinha a matriz errado (padding nativo); aqui vai
    # o formato que o proprio unpack dela (e o OpenRGB real) usa.
    data = u.pack_string(self.name) + struct.pack("<i3I", self.zone_type, self.leds_min, self.leds_max, self.num_leds)
    if self.mat_height:
        flat = [i for row in self.matrix_map for i in row]
        data += struct.pack(f"<HII{len(flat)}I", 8 + 4 * len(flat), self.mat_height, self.mat_width, *flat)
    else:
        data += struct.pack("<H", 0)
    if version >= 4:
        data += u.pack_list(self.segments, version)
    return data
u.ZoneData.pack = pack_zone
u.ModeData.validate = lambda self, version: None  # a validacao da biblioteca recusa brilho abaixo da v3

DEVICES = [
    device("Placa-mae ACME", [("Fita ARGB 1", 8, None), ("Chipset", 2, None)]),
    device("Teclado ACME", [("Teclas", 12, (3, 4))]),
    device("Memoria ACME", [("RAM", 5, None)]),
    device("Controladora ACME 2CH", [("Canal 1", 0, "ajustavel"), ("Canal 2", 0, "ajustavel")]),
]

def read_mode(data, v):
    """Le o pacote de modo (1101/1102): devolve (indice, nome, velocidade, brilho, cores)."""
    total, idx, n = struct.unpack_from("<IiH", data, 0)
    check(total == len(data), f"modo: tamanho interno {total} != {len(data)}")
    p = 10
    name = data[p:p + n].rstrip(b"\0").decode(); p += n
    p += 16                                   # valor, flags, vel_min, vel_max
    if v >= 3: p += 8                         # brilho_min, brilho_max
    p += 8                                    # cores_min, cores_max
    speed = struct.unpack_from("<I", data, p)[0]; p += 4
    bright = None
    if v >= 3:
        bright = struct.unpack_from("<I", data, p)[0]; p += 4
    p += 8                                    # direcao, modo de cor
    nc = struct.unpack_from("<H", data, p)[0]; p += 2
    check(len(data) == p + 4 * nc, f"modo: sobram ou faltam bytes ({len(data)} vs {p + 4 * nc})")
    return idx, name, speed, bright, [data[p + 4 * i:p + 4 * i + 3].hex() for i in range(nc)]

def resize(d, zi, n):
    z = d.zones[zi]
    check(z.leds_min <= n <= z.leds_max, f"zona {z.name}: {n} LEDs fora de {z.leds_min}..{z.leds_max}")
    z.num_leds = z.leds_count = n
    d.leds = [u.LEDData(f"{zz.name} {i}", i) for zz in d.zones for i in range(zz.num_leds)]
    d.colors = [u.RGBColor(0, 0, 0)] * len(d.leds)

def recvn(c, n):
    b = b""
    while len(b) < n:
        d = c.recv(n - len(b))
        if not d:
            raise EOFError
        b += d
    return b

def reply(c, dev, pid, data):
    c.sendall(b"ORGB" + struct.pack("<III", dev, pid, len(data)) + data)

for v in range(5):  # confere com o leitor da biblioteca de referencia
    for d in DEVICES:
        r = u.ControllerData.unpack(d.pack(v), v)
        assert r.name == d.name and len(r.colors) == len(d.colors) and len(r.zones) == len(d.zones)

def check(cond, msg):
    if not cond:
        raise ValueError(msg)

def handle(c, who):
    frames = {}
    ver = 0
    try:
        # aviso assincrono, que o cliente deve ignorar
        reply(c, 0, 100, b"")
        while True:
            magic, dev, pid, size = struct.unpack("<4sIII", recvn(c, 16))
            check(magic == b"ORGB", f"cabecalho invalido {magic!r}")
            data = recvn(c, size)
            if pid in (1, 1000, 1050, 1100, 1101, 1102):
                check(dev < len(DEVICES), f"dispositivo {dev} nao existe (ha {len(DEVICES)})")
            if pid == 40:
                check(size == 4, f"pacote 40 com {size} bytes")
                print(f"{who} versao pedida:", struct.unpack("<I", data)[0], flush=True)
                ver = min(struct.unpack("<I", data)[0], SERVER_PROTO)
                reply(c, 0, 40, struct.pack("<I", SERVER_PROTO))
            elif pid == 50:
                print(f"{who} cliente:", data, flush=True)
            elif pid == 0:
                reply(c, 0, 0, struct.pack("<I", len(DEVICES)))
            elif pid == 1:
                check(size in (0, 4), f"pacote 1 com {size} bytes")
                v = min(struct.unpack("<I", data)[0], SERVER_PROTO) if size else 0
                reply(c, dev, 1, DEVICES[dev].pack(v))
            elif pid in (150, 200):
                # lista de perfis / plugins: responde vazia para o cliente nao travar
                print(f"{who} pedido {pid}: lista vazia", flush=True)
                reply(c, 0, pid, struct.pack("<IH", 6, 0))
            elif pid == 1000:
                check(size == 8, f"pacote 1000 com {size} bytes")
                zi, n = struct.unpack("<ii", data)
                check(0 <= zi < len(DEVICES[dev].zones), f"dev {dev} nao tem zona {zi}")
                resize(DEVICES[dev], zi, n)
                print(f"{who} dev {dev}: zona {zi} agora com {n} LEDs", flush=True)
            elif pid in (1101, 1102):
                idx, name, speed, bright, cols = read_mode(data, ver)
                check(0 <= idx < len(DEVICES[dev].modes), f"dev {dev} nao tem modo {idx}")
                check(DEVICES[dev].modes[idx].name == name, f"modo {idx} se chama outra coisa que {name!r}")
                DEVICES[dev].active_mode = idx
                print(f"{who} dev {dev}: {'GRAVAR' if pid == 1102 else 'modo'} {name} "
                      f"vel={speed} brilho={bright} cores={cols}", flush=True)
            elif pid == 1100:
                check(size == 0, f"pacote 1100 com {size} bytes")
                print(f"{who} dev {dev}: modo custom", flush=True)
            elif pid == 1050:
                check(size >= 6, f"pacote 1050 com {size} bytes")
                total, n = struct.unpack("<IH", data[:6])
                check(total == size == 6 + 4 * n, f"tamanhos nao batem: total={total} size={size} n={n}")
                check(n == len(DEVICES[dev].leds),
                      f"dev {dev} tem {len(DEVICES[dev].leds)} LEDs, quadro veio com {n}")
                cols = [data[6 + 4 * i: 9 + 4 * i].hex() for i in range(n)]
                frames[dev] = frames.get(dev, 0) + 1
                if frames[dev] <= 6:
                    print(f"{who} dev {dev}: {' '.join(cols)}", flush=True)
            else:
                print(f"{who} pacote inesperado", pid, flush=True)
    except EOFError:
        pass
    except OSError as e:
        print(f"{who} conexao caiu: {type(e).__name__}", flush=True)
    except (ValueError, struct.error) as e:
        print(f"{who} ERRO DO CLIENTE: {e}", flush=True)
    finally:
        c.close()
        print(f"{who} desconectou apos {sum(frames.values())} quadros {frames}", flush=True)

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", PORT)); srv.listen(5)
print("mock ouvindo em", PORT, flush=True)
n = 0
while True:
    c, _ = srv.accept()
    n += 1
    threading.Thread(target=handle, args=(c, f"[{n}]"), daemon=True).start()
