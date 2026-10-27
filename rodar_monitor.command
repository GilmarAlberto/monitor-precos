#!/usr/bin/env bash
# Rodar o monitor no Mac: dois cliques neste arquivo.
# Na primeira vez prepara tudo sozinho; nas próximas, só roda.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 não encontrado. Baixe em https://www.python.org/downloads/ e instale."
    read -rp "Aperte Enter para fechar."
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Primeira vez: preparando o monitor (leva alguns minutos)..."
    python3 -m venv .venv &&
    .venv/bin/pip install -q -r requirements.txt &&
    .venv/bin/playwright install chromium || {
        echo "Não consegui preparar o monitor. Confira a internet e tente de novo."
        rm -rf .venv
        read -rp "Aperte Enter para fechar."
        exit 1
    }
fi

.venv/bin/python monitor.py --demo --mostrar "$@"
read -rp "Pronto. Aperte Enter para fechar."
