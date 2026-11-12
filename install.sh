#!/usr/bin/env sh
# Installerar stil-lab på Linux/macOS: verifierar Python, skapar startare, kör rökprov.
# Inga paket behöver installeras — allt använder Pythons standardbibliotek.
set -e

cd "$(dirname "$0")"

printf '\n  stil-lab\n  --------------------------------------------------\n\n'

PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver=$("$cand" -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null || true)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ -n "$ver" ] && { [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; }; }; then
            PY="$cand"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    printf '  Python 3.10 eller nyare hittades inte.\n  Installera och kör om.\n' >&2
    exit 1
fi
printf '  Python %s hittad (%s)\n' "$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')" "$PY"

cat > stil <<EOF
#!/usr/bin/env sh
cd "\$(dirname "\$0")" || exit 1
exec $PY -m src.cli "\$@"
EOF
chmod +x stil
printf '  Startare skapad: ./stil\n'

if [ ! -f out/stil.db ]; then
    printf '  Varning: out/stil.db saknas. Kör ./stil build först.\n'
    exit 0
fi

printf '\n  Rökprov:\n'
$PY -m src.cli stats --db out/stil.db | head -4

printf '\n  Klart. Prova:\n'
printf '    ./stil search "regnet mot fonstret" -k 5\n'
printf '    ./stil prompt "tva personer i en bil pa natten" -k 3\n\n'
