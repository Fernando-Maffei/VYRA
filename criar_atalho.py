"""Cria o atalho "VYRA", com o icone do programa, que abre o estudio sem janela de console.

Uso:
  python criar_atalho.py              # Area de Trabalho e Menu Iniciar
  python criar_atalho.py --aqui       # so na pasta do projeto
  python criar_atalho.py --remover    # apaga os atalhos criados por este script
"""
import argparse, ctypes, os, subprocess, sys

PASTA = os.path.dirname(os.path.abspath(__file__))
NOME = "VYRA.lnk"


def destinos(aqui):
    if aqui:
        return [PASTA]
    menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    return [p for p in (area_de_trabalho(), menu) if p and os.path.isdir(p)]


def area_de_trabalho():
    """Pasta da Area de Trabalho direto do Windows (funciona com OneDrive e nomes acentuados)."""
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:     # CSIDL_DESKTOPDIRECTORY
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def criar(pasta):
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    lnk = os.path.join(pasta, NOME)
    script = f"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}')
$s.TargetPath = '{pythonw}'
$s.Arguments = '"{os.path.join(PASTA, "luz_estudio.pyw")}"'
$s.WorkingDirectory = '{PASTA}'
$s.IconLocation = '{os.path.join(PASTA, "assets", "vyra.ico")},0'
$s.Description = 'VYRA - Unified Lighting'
$s.Save()
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Nao foi possivel criar {lnk}:\n{r.stderr}")
    print("Atalho criado:", lnk)


def main():
    p = argparse.ArgumentParser(description="Cria o atalho do VYRA com o icone do programa.")
    p.add_argument("--aqui", action="store_true", help="cria so na pasta do projeto")
    p.add_argument("--remover", action="store_true", help="remove os atalhos criados")
    a = p.parse_args()
    for pasta in destinos(a.aqui):
        if a.remover:
            lnk = os.path.join(pasta, NOME)
            if os.path.isfile(lnk):
                os.remove(lnk)
                print("Atalho removido:", lnk)
        else:
            criar(pasta)


if __name__ == "__main__":
    main()
