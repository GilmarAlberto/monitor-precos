"""Três lojas de fornecedores de mentira, para demonstrar o robô.

Cada loja mostra os produtos de um jeito diferente, como na vida real:
- Atacadão do Escritório: uma tabela simples
- MegaInfo Distribuidora: cartões, divididos em duas páginas
- Papelaria Central: uma lista; costuma falhar na primeira visita

Os preços mudam a cada vez que as lojas são ligadas (uma "rodada"),
para o robô ter o que comparar entre uma coleta e outra.

Uso: python lojas/app.py   (abre em http://127.0.0.1:5001)
Para simular uma loja fora do ar: LOJAS_FORA=papelaria python lojas/app.py
"""
import json
import os
import random
from pathlib import Path

from flask import Flask, abort, render_template, request

app = Flask(__name__)

# EAN, descrição e preço de referência
CATALOGO = [
    ("7891000000011", "Papel A4 75 g (caixa com 10 resmas)", 289.90),
    ("7891000000028", "Toner compatível 85A", 89.90),
    ("7891000000035", "Mouse sem fio 1600 dpi", 69.90),
    ("7891000000042", "Teclado USB ABNT2", 59.90),
    ("7891000000059", "Cabo HDMI 2 metros", 24.90),
    ("7891000000066", "SSD 480 GB SATA", 219.90),
    ("7891000000073", "Pen drive 64 GB", 39.90),
    ("7891000000080", "Caneta esferográfica azul (caixa com 50)", 44.90),
]

LOJAS = {
    "atacadao": {"nome": "Atacadão do Escritório", "fator": 1.00, "prefixo": "AT-10",
                 "nao_vende": set()},
    "megainfo": {"nome": "MegaInfo Distribuidora", "fator": 0.97, "prefixo": "MI-55",
                 "nao_vende": {"7891000000080"}},
    "papelaria": {"nome": "Papelaria Central", "fator": 1.04, "prefixo": "PC00",
                  "nao_vende": {"7891000000066"}},
}

POR_PAGINA = 4                                  # a MegaInfo mostra 4 produtos por página
ARQUIVO_RODADA = Path(__file__).with_name("rodada.json")
FORA_DO_AR = {loja.strip() for loja in os.environ.get("LOJAS_FORA", "").split(",") if loja}


def proxima_rodada():
    rodada = 1
    if ARQUIVO_RODADA.exists():
        rodada = json.loads(ARQUIVO_RODADA.read_text())["rodada"] + 1
    ARQUIVO_RODADA.write_text(json.dumps({"rodada": rodada}))
    return rodada


RODADA = proxima_rodada()
primeira_visita = {"papelaria": True}


def preco(loja, ean, base):
    """Parte do preço de referência e, a cada rodada, metade das vezes muda um pouco."""
    valor = base * LOJAS[loja]["fator"]
    for rodada in range(2, RODADA + 1):
        sorteio = random.Random(f"{rodada}-{loja}-{ean}")
        if sorteio.random() < 0.5:
            valor *= 1 + sorteio.choice([-1, 1]) * sorteio.uniform(0.03, 0.12)
    return round(int(valor) + 0.90, 2)           # preço de vitrine: sempre ,90


def produtos_da_loja(loja):
    dados = LOJAS[loja]
    lista = []
    for numero, (ean, descricao, base) in enumerate(CATALOGO, start=1):
        if ean in dados["nao_vende"]:
            continue
        disponivel = random.Random(f"estoque-{RODADA}-{loja}-{ean}").random() > 0.12
        lista.append({"codigo": f"{dados['prefixo']}{numero:02d}", "ean": ean,
                      "descricao": descricao, "preco": preco(loja, ean, base),
                      "disponivel": disponivel})
    return lista


@app.template_filter("reais")
def reais(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.before_request
def simular_falhas():
    loja = request.path.strip("/").split("/")[0]
    if loja in FORA_DO_AR:
        abort(503)
    if primeira_visita.get(loja):                 # cai na primeira visita, volta na segunda
        primeira_visita[loja] = False
        abort(503)


@app.errorhandler(503)
def fora_do_ar(_erro):
    return render_template("fora_do_ar.html"), 503


@app.route("/")
def inicio():
    return render_template("inicio.html", lojas=LOJAS, rodada=RODADA)


@app.route("/atacadao")
def atacadao():
    return render_template("atacadao.html", produtos=produtos_da_loja("atacadao"))


@app.route("/megainfo")
def megainfo():
    produtos = produtos_da_loja("megainfo")
    pagina = request.args.get("pagina", 1, type=int)
    inicio_da_pagina = (pagina - 1) * POR_PAGINA
    return render_template("megainfo.html", pagina=pagina,
                           produtos=produtos[inicio_da_pagina:inicio_da_pagina + POR_PAGINA],
                           tem_proxima=inicio_da_pagina + POR_PAGINA < len(produtos))


@app.route("/papelaria")
def papelaria():
    return render_template("papelaria.html", produtos=produtos_da_loja("papelaria"))


if __name__ == "__main__":
    app.run(port=5001)
