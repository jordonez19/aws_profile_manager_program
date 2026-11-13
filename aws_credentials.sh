#!/bin/bash

REGION="us-east-1"

# =====================================================================
#  Estilos (se desactivan solos si no es una terminal o si NO_COLOR=1)
# =====================================================================
if [ -t 1 ] && [ -z "$NO_COLOR" ]; then
    RST=$'\033[0m';  BOLD=$'\033[1m';  DIM=$'\033[2m'
    RED=$'\033[38;5;203m';    GREEN=$'\033[38;5;114m'
    YELLOW=$'\033[38;5;221m'; BLUE=$'\033[38;5;75m'
    CYAN=$'\033[38;5;80m';    ORANGE=$'\033[38;5;208m'
    GRAY=$'\033[38;5;245m';   WHITE=$'\033[97m'
else
    RST=""; BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""
    BLUE=""; CYAN=""; ORANGE=""; GRAY=""; WHITE=""
fi

line()  { printf '  %s%s%s\n' "$GRAY" "──────────────────────────────────────────────────" "$RST"; }
title() { echo; printf '  %s%s◆ %s%s\n' "$BOLD" "$ORANGE" "$1" "$RST"; line; }
info()  { printf '  %sℹ%s  %s\n' "$BLUE"   "$RST" "$1"; }
ok()    { printf '  %s✔%s  %s\n' "$GREEN"  "$RST" "$1"; }
warn()  { printf '  %s⚠%s  %s\n' "$YELLOW" "$RST" "$1"; }
err()   { printf '  %s✖%s  %s\n' "$RED"    "$RST" "$1"; }
opt()   { printf '    %s%s[%s]%s %s\n' "$BOLD" "$CYAN" "$1" "$RST" "$2"; }
kv()    { printf '    %s%-15s%s %s\n' "$GRAY" "$1" "$RST" "$2"; }

# ask VARIABLE "Texto de la pregunta"
ask() {
    local __var="$1"; shift
    read -rp "  ${ORANGE}❯${RST} ${BOLD}$*${RST} " "$__var"
}

# Oculta la mayor parte de una credencial al mostrarla
mask() {
    local s="$1"
    if [ ${#s} -le 8 ]; then
        echo "••••••••"
    else
        echo "${s:0:4}••••••••${s: -4}"
    fi
}

# Lista de profiles con formato (resalta 'default')
print_profiles() {
    local i="${1:-1}"
    for p in "${PROFILES[@]}"; do
        if [ "$p" == "default" ]; then
            opt "$i" "${WHITE}$p${RST} ${DIM}(default)${RST}"
        else
            opt "$i" "${WHITE}$p${RST}"
        fi
        ((i++))
    done
}

banner() {
    echo
    printf '%s%s' "$ORANGE" "$BOLD"
    cat <<'EOF'
          █████╗ ██╗    ██╗███████╗
         ██╔══██╗██║    ██║██╔════╝
         ███████║██║ █╗ ██║███████╗
         ██╔══██║██║███╗██║╚════██║
         ██║  ██║╚███╔███╔╝███████║
         ╚═╝  ╚═╝ ╚══╝╚══╝ ╚══════╝
EOF
    printf '%s' "$RST"
    printf '     %s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$GRAY" "$RST"
    printf '       %s%s🔐 AUTENTICACIÓN DE CREDENCIALES%s\n' "$BOLD" "$WHITE" "$RST"
    printf '          %sProfile Manager · %s%s\n' "$DIM" "$REGION" "$RST"
    printf '     %s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$GRAY" "$RST"
}

banner

# --- Selección o creación de profile ---
mapfile -t PROFILES < <(aws configure list-profiles 2>/dev/null | tr -d '\r')

# Fallback: si el subcomando no devolvió nada, leemos el archivo directamente
if [ ${#PROFILES[@]} -eq 0 ]; then
    CRED_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}"
    if [ -f "$CRED_FILE" ]; then
        mapfile -t PROFILES < <(grep -oE '^\[[^]]+\]' "$CRED_FILE" | tr -d '[]\r')
    fi
fi

cleanup_profiles() {
    local CRED_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}"
    local CONFIG_FILE="${AWS_CONFIG_FILE:-$HOME/.aws/config}"

    title "Limpiar profiles"
    print_profiles
    echo
    printf '    %sOpciones:%s\n' "$DIM" "$RST"
    printf '    %s• números separados por coma  %s(ej: 1,3,5)%s\n' "$GRAY" "$DIM" "$RST"
    printf '    %s• %stodos%s%s          → todos menos %sdefault%s\n' "$GRAY" "$YELLOW" "$RST" "$GRAY" "$WHITE" "$RST"
    printf '    %s• %stodo-absoluto%s%s  → incluye %sdefault%s\n' "$GRAY" "$RED" "$RST" "$GRAY" "$WHITE" "$RST"
    printf '    %s• %scancelar%s\n' "$GRAY" "$CYAN" "$RST"
    echo
    ask DEL_INPUT "¿Qué profiles quieres BORRAR?"

    if [ -z "$DEL_INPUT" ] || [ "$DEL_INPUT" == "cancelar" ]; then
        info "Cancelado, no se borró nada."
        return
    fi

    local TO_DELETE=()
    if [ "$DEL_INPUT" == "todos" ]; then
        for p in "${PROFILES[@]}"; do
            [ "$p" != "default" ] && TO_DELETE+=("$p")
        done
    elif [ "$DEL_INPUT" == "todo-absoluto" ]; then
        TO_DELETE=("${PROFILES[@]}")
    else
        IFS=',' read -ra NUMS <<< "$DEL_INPUT"
        for n in "${NUMS[@]}"; do
            n="$(echo "$n" | tr -d '[:space:]')"
            if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le ${#PROFILES[@]} ]; then
                TO_DELETE+=("${PROFILES[$((n-1))]}")
            fi
        done
    fi

    if [ ${#TO_DELETE[@]} -eq 0 ]; then
        warn "No se reconoció ningún profile válido para borrar."
        return
    fi

    echo
    warn "Se van a borrar: ${RED}${BOLD}${TO_DELETE[*]}${RST}"
    ask CONFIRM "¿Confirmas? (s/N):"
    if [[ ! "$CONFIRM" =~ ^[sS]$ ]]; then
        info "Cancelado, no se borró nada."
        return
    fi

    local CREATE_BACKUP="n"
    local TS=""
    ask CREATE_BACKUP "¿Guardar un backup de las credenciales anteriores? (s/N):"

    if [[ "$CREATE_BACKUP" =~ ^[sS]$ ]]; then
        TS="$(date +%Y%m%d%H%M%S)"
        [ -f "$CRED_FILE" ] && cp "$CRED_FILE" "${CRED_FILE}.bak.${TS}"
        [ -f "$CONFIG_FILE" ] && cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.${TS}"
    fi

    printf '  %s' "$GRAY"
    python3 - "$CRED_FILE" "$CONFIG_FILE" "${TO_DELETE[@]}" <<'PYEOF'
import configparser
import sys

cred_file, config_file, *to_delete = sys.argv[1:]

# credentials: secciones = [nombre]
cp = configparser.RawConfigParser()
cp.read(cred_file)
for name in to_delete:
    cp.remove_section(name)
with open(cred_file, "w") as f:
    cp.write(f)

# config: secciones = [profile nombre], excepto [default]
cp2 = configparser.RawConfigParser()
cp2.read(config_file)
for name in to_delete:
    section = "default" if name == "default" else f"profile {name}"
    cp2.remove_section(section)
with open(config_file, "w") as f:
    cp2.write(f)

print("Borrados:", ", ".join(to_delete))
PYEOF
    printf '%s' "$RST"

    if [[ "$CREATE_BACKUP" =~ ^[sS]$ ]]; then
        ok "🗑️  Listo. Backups guardados con la extensión ${CYAN}.bak.${TS}${RST}"
    else
        ok "🗑️  Listo. Los profiles se borraron sin crear backups."
    fi

    # Refrescar la lista de profiles
    mapfile -t PROFILES < <(aws configure list-profiles 2>/dev/null | tr -d '\r')
}

PROFILE=""
while [ -z "$PROFILE" ]; do
    if [ ${#PROFILES[@]} -eq 0 ]; then
        title "Nuevo profile"
        info "No se encontraron profiles existentes."
        ask PROFILE "Nombre del nuevo profile:"
    else
        title "Selecciona un profile"
        opt "0" "${YELLOW}🧹 Limpiar profiles antiguos${RST} ${DIM}(borrar los que no uses)${RST}"
        opt "1" "${GREEN}＋ Crear un profile nuevo${RST}"
        print_profiles 2
        echo
        ask OPTION "Selecciona una opción:"

        if [ "$OPTION" == "0" ]; then
            cleanup_profiles
            continue
        elif [ "$OPTION" == "1" ]; then
            ask PROFILE "Nombre del nuevo profile:"
        elif [[ "$OPTION" =~ ^[0-9]+$ ]] && [ "$OPTION" -ge 2 ] && [ "$OPTION" -le $(( ${#PROFILES[@]} + 1 )) ]; then
            PROFILE="${PROFILES[$((OPTION-2))]}"
        else
            ask PROFILE "Nombre del nuevo profile:"
        fi
    fi
done

if [ -z "$PROFILE" ]; then
    err "Error: debes indicar un nombre de profile."
    exit 1
fi

title "Credenciales para [${WHITE}${PROFILE}${ORANGE}]"
info "Pega las credenciales de AWS ${DIM}(Access Key, Secret Key y Session Token)${RST}"
info "Presiona ${BOLD}Enter dos veces${RST} cuando termines."
printf '  %s┌─ pega aquí ───────────────────────────────────%s\n' "$GRAY" "$RST"

# Leer todas las líneas hasta que se encuentre una línea vacía
CREDENTIALS=""
while IFS= read -r line; do
    if [ -z "$line" ]; then
        break
    fi
    CREDENTIALS="$CREDENTIALS$line"$'\n'
done
printf '  %s└───────────────────────────────────────────────%s\n' "$GRAY" "$RST"

# Extraer las credenciales usando expresiones regulares
ACCESS_KEY=$(echo "$CREDENTIALS" | grep -o 'export AWS_ACCESS_KEY_ID=.*' | cut -d'=' -f2 | tr -d '"')
SECRET_KEY=$(echo "$CREDENTIALS" | grep -o 'export AWS_SECRET_ACCESS_KEY=.*' | cut -d'=' -f2 | tr -d '"')
SESSION_TOKEN=$(echo "$CREDENTIALS" | grep -o 'export AWS_SESSION_TOKEN=.*' | cut -d'=' -f2 | tr -d '"')

if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    err "Error: No se pudieron extraer las credenciales correctamente"
    exit 1
fi

title "Resumen"
kv "Profile"       "${WHITE}${PROFILE}${RST}"
kv "Access Key"    "$(mask "$ACCESS_KEY")"
kv "Secret Key"    "$(mask "$SECRET_KEY")"
if [ -n "$SESSION_TOKEN" ]; then
    kv "Session Token" "${GREEN}presente${RST}"
else
    kv "Session Token" "${DIM}no incluido${RST}"
fi
kv "Región"        "$REGION"
kv "Output"        "json"
echo

aws configure set aws_access_key_id "$ACCESS_KEY" --profile "$PROFILE"
aws configure set aws_secret_access_key "$SECRET_KEY" --profile "$PROFILE"
aws configure set region "$REGION" --profile "$PROFILE"
aws configure set output "json" --profile "$PROFILE"

if [ -n "$SESSION_TOKEN" ]; then
  aws configure set aws_session_token "$SESSION_TOKEN" --profile "$PROFILE"
fi

ok "Credenciales configuradas en el profile ${BOLD}[$PROFILE]${RST}."

title "Verificando conexión"
if IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" --output json 2>&1); then
    ACCOUNT=$(echo "$IDENTITY" | grep -o '"Account": *"[^"]*"' | cut -d'"' -f4)
    ARN=$(echo "$IDENTITY"     | grep -o '"Arn": *"[^"]*"'     | cut -d'"' -f4)
    USERID=$(echo "$IDENTITY"  | grep -o '"UserId": *"[^"]*"'  | cut -d'"' -f4)
    ok "${GREEN}${BOLD}Conexión exitosa${RST}"
    echo
    kv "Account" "${WHITE}${ACCOUNT}${RST}"
    kv "UserId"  "$USERID"
    kv "Arn"     "${CYAN}${ARN}${RST}"
else
    err "${RED}${BOLD}No se pudo verificar la conexión${RST}"
    printf '%s%s%s\n' "$DIM" "$IDENTITY" "$RST" | sed 's/^/    /'
fi

while true; do
    title "¿Qué deseas hacer?"
    opt "1" "Terminar"
    opt "2" "Registrar o actualizar otro profile"
    echo
    ask NEXT_ACTION "Selecciona una opción:"

    case "$NEXT_ACTION" in
        1)
            echo
            printf '  %s%s👋 Finalizado.%s\n\n' "$BOLD" "$ORANGE" "$RST"
            exit 0
            ;;
        2)
            exec "$0"
            ;;
        *)
            warn "Opción inválida. Ingresa 1 o 2."
            ;;
    esac
done
