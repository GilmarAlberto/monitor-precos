"""Histórico das coletas num banco SQLite (um arquivo só, sem instalar nada)."""
import sqlite3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS coletas (
    id        INTEGER PRIMARY KEY,
    data_hora TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS precos (
    coleta     INTEGER NOT NULL REFERENCES coletas(id),
    loja       TEXT NOT NULL,
    codigo     TEXT,
    ean        TEXT NOT NULL,
    produto    TEXT NOT NULL,
    preco      REAL,                  -- vazio quando a loja não mostra o preço
    disponivel INTEGER NOT NULL,
    UNIQUE (coleta, loja, ean)        -- o mesmo produto não entra duas vezes na coleta
);
CREATE TABLE IF NOT EXISTS falhas (
    coleta INTEGER NOT NULL REFERENCES coletas(id),
    loja   TEXT NOT NULL,
    motivo TEXT NOT NULL,
    print  TEXT
);
"""


def abrir(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    banco = sqlite3.connect(caminho)
    banco.row_factory = sqlite3.Row
    banco.executescript(ESQUEMA)
    return banco


def nova_coleta(banco, data_hora):
    return banco.execute("INSERT INTO coletas (data_hora) VALUES (?)",
                         (data_hora.strftime("%Y-%m-%d %H:%M:%S"),)).lastrowid


def gravar_precos(banco, coleta, loja, itens):
    banco.executemany(
        "INSERT OR IGNORE INTO precos VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(coleta, loja, i["codigo"], i["ean"], i["produto"], i["preco"], i["disponivel"])
         for i in itens])


def gravar_falha(banco, coleta, loja, motivo, imagem):
    banco.execute("INSERT INTO falhas VALUES (?, ?, ?, ?)", (coleta, loja, motivo, imagem))


def precos_da_coleta(banco, coleta, loja=None):
    sql = "SELECT * FROM precos WHERE coleta = ?" + (" AND loja = ?" if loja else "")
    return banco.execute(sql, (coleta, loja) if loja else (coleta,)).fetchall()


def coleta_anterior(banco, coleta, loja):
    """A última coleta, antes desta, em que a loja respondeu."""
    linha = banco.execute("SELECT MAX(coleta) FROM precos WHERE loja = ? AND coleta < ?",
                          (loja, coleta)).fetchone()
    return linha[0]


def variacoes(banco, coleta, lojas_coletadas):
    """Compara cada loja com a coleta anterior dela: o que subiu, baixou, sumiu ou voltou."""
    mudancas = []
    for loja in lojas_coletadas:
        anterior = coleta_anterior(banco, coleta, loja)
        if anterior is None:
            continue                                    # primeira vez: não há com o que comparar
        antes = {p["ean"]: p for p in precos_da_coleta(banco, anterior, loja)}
        agora = {p["ean"]: p for p in precos_da_coleta(banco, coleta, loja)}
        for ean in sorted(antes.keys() | agora.keys()):
            a, d = antes.get(ean), agora.get(ean)
            situacao = None
            if a is None:
                situacao = "Produto novo"
            elif d is None:
                situacao = "Saiu do site"
            elif a["disponivel"] and not d["disponivel"]:
                situacao = "Ficou indisponível"
            elif not a["disponivel"] and d["disponivel"]:
                situacao = "Voltou ao estoque"
            elif d["disponivel"] and d["preco"] != a["preco"]:
                situacao = "Subiu" if d["preco"] > a["preco"] else "Baixou"
            if situacao:
                mudancas.append({
                    "loja": loja, "produto": (d or a)["produto"], "ean": ean,
                    "antes": a["preco"] if a and a["disponivel"] else None,
                    "agora": d["preco"] if d and d["disponivel"] else None,
                    "situacao": situacao})
    return mudancas


def historico(banco):
    return banco.execute("""
        SELECT c.data_hora, p.loja, p.ean, p.produto, p.preco, p.disponivel
          FROM precos p JOIN coletas c ON c.id = p.coleta
         ORDER BY p.produto, p.loja, c.data_hora""").fetchall()
