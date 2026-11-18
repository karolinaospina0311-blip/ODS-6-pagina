import sys
from pathlib import Path

import psycopg

if len(sys.argv) < 2:
    print("Uso: python backend/restaurar_dump.py \"$DATABASE_URL\"")
    raise SystemExit(2)

url = sys.argv[1]
archivo = Path(__file__).resolve().parent.parent / "database" / "ecoagua_dump.sql"
ok = 0
errores = 0

with psycopg.connect(url, autocommit=True) as conn:
    cur = conn.cursor()
    buffer = []
    en_copy = False
    copy_sql = ""
    copy_data = []

    with open(archivo, encoding="utf-8-sig") as f:
        for linea in f:
            if en_copy:
                if linea.rstrip("\n") == "\\.":
                    try:
                        with cur.copy(copy_sql) as cp:
                            cp.write("".join(copy_data))
                        ok += 1
                    except Exception as e:
                        errores += 1
                        print("ERROR COPY:", copy_sql[:70], "->", str(e)[:120])
                    en_copy = False
                    copy_data = []
                else:
                    copy_data.append(linea)
                continue

            s = linea.strip()
            if not buffer and (not s or s.startswith("--") or s.startswith("\\")):
                continue
            if not buffer and s.upper().startswith("COPY ") and s.endswith("FROM stdin;"):
                copy_sql = s
                en_copy = True
                continue

            buffer.append(linea)
            texto = "".join(buffer)
            if s.endswith(";") and texto.count("$$") % 2 == 0:
                try:
                    cur.execute(texto)
                    ok += 1
                except Exception as e:
                    errores += 1
                    print("ERROR:", texto.strip()[:80], "->", str(e)[:120])
                buffer = []

    print(f"\nListo. Sentencias correctas: {ok}. Con error: {errores}\n")
    cur.execute("select tablename from pg_tables where schemaname='public' order by 1")
    for (t,) in cur.fetchall():
        n = conn.execute(f'select count(*) from public."{t}"').fetchone()[0]
        print(f"{t}: {n} filas")