"""Robô que monitora os preços de fornecedores e compara as ofertas.

Visita o site de cada fornecedor, anota nome, código, EAN, preço e
disponibilidade de cada produto, guarda tudo no histórico (SQLite) e
gera a planilha saida/relatorio_precos.xlsx com as melhores ofertas,
a comparação entre as lojas e o que mudou desde a última coleta.
Se um site falhar, tenta de novo; se continuar fora, registra e segue.

Uso:
    python monitor.py             roda sem abrir a janela do navegador
    python monitor.py --mostrar   abre o navegador e vai devagar, para acompanhar
    python monitor.py --demo      liga junto as lojas de demonstração
"""
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as Demorou
from playwright.sync_api import sync_playwright

import historico
from relatorio import gerar_relatorio

ENDERECO = os.environ.get("MONITOR_ENDERECO", "http://127.0.0.1:5001")
TENTATIVAS = 3              # se o site falhar, tenta mais duas vezes
ESPERA_ENTRE_TENTATIVAS = 2_000
ESPERA_MAXIMA = 15_000      # milissegundos

PASTA_SAIDA = Path("saida")
PASTA_ERROS = PASTA_SAIDA / "erros"
BANCO = PASTA_SAIDA / "historico.db"
RELATORIO = PASTA_SAIDA / "relatorio_precos.xlsx"

log = logging.getLogger("monitor")


class SiteComProblema(Exception):
    pass


def configurar_log():
    PASTA_ERROS.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%d/%m/%Y %H:%M:%S")
    for destino in (logging.FileHandler(PASTA_SAIDA / "monitor.log", encoding="utf-8"),
                    logging.StreamHandler(sys.stdout)):
        destino.setFormatter(formato)
        log.addHandler(destino)
    log.setLevel(logging.INFO)


def para_numero(texto):
    """'R$ 1.219,90' ou '32,90 à vista' -> 1219.9 / 32.9"""
    achado = re.search(r"\d[\d.]*,\d{2}", texto)
    return float(achado.group().replace(".", "").replace(",", ".")) if achado else None


def abrir(pagina, caminho):
    resposta = pagina.goto(ENDERECO + caminho)
    if resposta is None or resposta.status >= 400:
        raise SiteComProblema(f"o site respondeu com erro {resposta.status if resposta else '?'}")


# Cada fornecedor mostra os produtos de um jeito; só estas funções mudam de site para site.

def coletar_atacadao(pagina):
    abrir(pagina, "/atacadao")
    itens = []
    for linha in pagina.locator("#tabela-precos tr.produto").all():
        itens.append({
            "codigo": linha.locator(".codigo").inner_text().strip(),
            "ean": linha.locator(".ean").inner_text().strip(),
            "produto": linha.locator(".descricao").inner_text().strip(),
            "preco": para_numero(linha.locator(".preco").inner_text()),
            "disponivel": linha.locator(".estoque").inner_text().strip() == "Disponível",
        })
    return itens


def coletar_megainfo(pagina):
    itens, caminho = [], "/megainfo?pagina=1"
    while caminho:                                   # percorre todas as páginas
        abrir(pagina, caminho)
        for card in pagina.locator(".card").all():
            valor = card.locator(".valor")
            itens.append({
                "codigo": card.locator(".sku").inner_text().replace("SKU", "").strip(),
                "ean": card.locator(".ean").inner_text().replace("EAN:", "").strip(),
                "produto": card.locator("h3").inner_text().strip(),
                "preco": para_numero(valor.inner_text()) if valor.count() else None,
                "disponivel": valor.count() > 0,
            })
        proxima = pagina.locator("#proxima")
        caminho = proxima.get_attribute("href") if proxima.count() else None
    return itens


def coletar_papelaria(pagina):
    abrir(pagina, "/papelaria")
    itens = []
    for item in pagina.locator("#lista li.item").all():
        valor = item.locator(".valor")
        itens.append({
            "codigo": item.get_attribute("data-codigo"),
            "ean": re.sub(r"\D", "", item.locator(".ean").inner_text()),
            "produto": item.locator(".nome").inner_text().strip(),
            "preco": para_numero(valor.inner_text()) if valor.count() else None,
            "disponivel": valor.count() > 0,
        })
    return itens


LOJAS = {
    "Atacadão do Escritório": coletar_atacadao,
    "MegaInfo Distribuidora": coletar_megainfo,
    "Papelaria Central": coletar_papelaria,
}


def coletar_loja(pagina, loja, coletar):
    """Devolve (itens, motivo da falha). Tenta de novo se o site falhar ou demorar."""
    motivo = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            itens = coletar(pagina)
            if not itens:
                raise SiteComProblema("nenhum produto encontrado: o site pode ter mudado")
            return itens, None
        except (SiteComProblema, Demorou) as erro:
            motivo = "o site não respondeu a tempo" if isinstance(erro, Demorou) else str(erro)
            log.warning("%s: %s (tentativa %d de %d)", loja, motivo, tentativa, TENTATIVAS)
            if tentativa < TENTATIVAS:
                pagina.wait_for_timeout(ESPERA_ENTRE_TENTATIVAS)
    return [], motivo


def planilha_aberta(caminho):
    """O Excel e o LibreOffice criam um arquivo de trava enquanto a planilha está aberta."""
    travas = (f"~${caminho.name}", f".~lock.{caminho.name}#")
    return any(caminho.with_name(trava).exists() for trava in travas)


def ligar_lojas_de_demonstracao():
    """Sobe as lojas de mentira junto com o robô, para a demonstração rodar com um clique só."""
    from werkzeug.serving import make_server

    sys.path.insert(0, str(Path(__file__).parent / "lojas"))
    from app import app

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    servidor = make_server("127.0.0.1", 5001, app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    log.info("Lojas de demonstração ligadas em %s", ENDERECO)


def main():
    mostrar = "--mostrar" in sys.argv
    configurar_log()
    if planilha_aberta(RELATORIO):
        log.error("Feche a planilha %s antes de rodar o robô: ele precisa gravar nela.", RELATORIO)
        sys.exit(1)
    if "--demo" in sys.argv:
        ligar_lojas_de_demonstracao()

    banco = historico.abrir(BANCO)
    agora = datetime.now()
    coleta = historico.nova_coleta(banco, agora)
    log.info("Coleta nº %d iniciada", coleta)

    lojas_ok, falhas = [], []
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=not mostrar,
                                               slow_mo=250 if mostrar else 0)
        pagina = navegador.new_page(viewport={"width": 1200, "height": 800})
        pagina.set_default_timeout(ESPERA_MAXIMA)

        for loja, coletar in LOJAS.items():
            itens, motivo = coletar_loja(pagina, loja, coletar)
            if motivo:
                imagem = str(PASTA_ERROS / f"coleta_{coleta:04d}_{re.sub(r'\W+', '_', loja)}.png")
                pagina.screenshot(path=imagem, full_page=True)
                historico.gravar_falha(banco, coleta, loja, motivo, imagem)
                falhas.append({"loja": loja, "motivo": motivo,
                               "print": os.path.relpath(imagem, RELATORIO.parent)})
                log.error("%s: não foi possível coletar (%s). Seguindo para a próxima loja.",
                          loja, motivo)
                continue
            historico.gravar_precos(banco, coleta, loja, itens)
            lojas_ok.append(loja)
            sem_estoque = sum(1 for i in itens if not i["disponivel"])
            log.info("%s: %d produtos coletados (%d sem estoque)", loja, len(itens), sem_estoque)
        navegador.close()
    banco.commit()

    mudancas = historico.variacoes(banco, coleta, lojas_ok)
    gerar_relatorio(RELATORIO, agora, list(LOJAS), historico.precos_da_coleta(banco, coleta),
                    mudancas, historico.historico(banco), falhas)
    banco.close()

    subiram = sum(1 for m in mudancas if m["situacao"] == "Subiu")
    baixaram = sum(1 for m in mudancas if m["situacao"] == "Baixou")
    log.info("Fim: %d de %d lojas coletadas. Desde a última coleta: %d preços subiram, "
             "%d baixaram. Relatório em %s", len(lojas_ok), len(LOJAS), subiram, baixaram,
             RELATORIO)


if __name__ == "__main__":
    main()
