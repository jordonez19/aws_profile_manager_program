# AWS Profile Manager

Aplicación de escritorio para administrar perfiles de AWS CLI (crear, editar,
verificar y borrar en `~/.aws/credentials` y `~/.aws/config`). Se puede ejecutar
desde Python, compilar a `.exe` o empaquetar en un instalador de Windows que no
requiere permisos de administrador.

## Archivos

- `aws_profile_manager.py`: aplicación de escritorio (Tkinter).
- `aws_credentials.sh`: versión de terminal (Bash) del mismo flujo.
- `aws-profile-manager-icon.ico` / `.png`: iconos del ejecutable y la ventana.
- `AWSProfileManager.iss`: configuración del instalador (Inno Setup).
- `build/` y `dist/`: se generan al compilar; se pueden borrar.

## Opción A: instalar todo y compilar (copiar y pegar)

Requisito previo: Windows con Python 3.8+ (comando `py`). Abre **PowerShell** y
pega todo el bloque:

```powershell
# 1. Ir a la carpeta del proyecto
Set-Location "$HOME\Desktop\aws_profile_manager_program"

# 2. Dependencias de Python
py -m pip install --upgrade pyinstaller boto3

# 3. Inno Setup 6 (solo si no está instalado), para crear el instalador
if (-not (Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
  winget install --id JRSoftware.InnoSetup -e --scope user --accept-package-agreements --accept-source-agreements
}

# 4. Generar el ejecutable (dist\AWSProfileManager.exe)
py -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name AWSProfileManager `
  --icon aws-profile-manager-icon.ico `
  --add-data "aws-profile-manager-icon.ico;." `
  --add-data "aws-profile-manager-icon.png;." `
  aws_profile_manager.py

# 5. Generar el instalador (dist\installer\AWSProfileManager-Setup.exe)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" .\AWSProfileManager.iss

# 6. Abrir el instalador
Start-Process .\dist\installer\AWSProfileManager-Setup.exe
```

Si `winget` instala Inno Setup en otra ruta (por ejemplo
`C:\Program Files (x86)\Inno Setup 6`), cambia la ruta de `ISCC.exe` en el
paso 5.

### Equivalente en Git Bash

```bash
cd ~/Desktop/aws_profile_manager_program

py -m pip install --upgrade pyinstaller boto3

py -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name AWSProfileManager \
  --icon aws-profile-manager-icon.ico \
  --add-data "aws-profile-manager-icon.ico;." \
  --add-data "aws-profile-manager-icon.png;." \
  aws_profile_manager.py

"$(cygpath -u "$LOCALAPPDATA")/Programs/Inno Setup 6/ISCC.exe" AWSProfileManager.iss

cmd.exe /c start "" "dist\\installer\\AWSProfileManager-Setup.exe"
```

## Opción B: ejecutar sin compilar

```powershell
Set-Location "$HOME\Desktop\aws_profile_manager_program"
py -m pip install boto3
py aws_profile_manager.py
```

`boto3` es opcional: permite "Verificar conexión" sin la AWS CLI. Sin él, la app
usa el comando `aws` si está en el PATH.

## Versión de terminal (`aws_credentials.sh`)

Misma gestión de profiles pero desde la terminal, sin ventana. Requiere
**AWS CLI** y **Python 3** (se usa para borrar profiles) en Git Bash, Linux o
macOS.

Instalar los requisitos en Windows (PowerShell, opcional si ya los tienes):

```powershell
winget install --id Amazon.AWSCLI -e
winget install --id Git.Git -e
```

Ejecutar (Git Bash, Linux o macOS):

```bash
cd ~/Desktop/aws_profile_manager_program
bash aws_credentials.sh
```

Opcional: dejarlo como comando `aws-creds` disponible desde cualquier carpeta:

```bash
mkdir -p ~/bin
cp ~/Desktop/aws_profile_manager_program/aws_credentials.sh ~/bin/aws-creds
chmod +x ~/bin/aws-creds
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
aws-creds
```

Cómo funciona:

- El menú muestra siempre `[0] Limpiar profiles antiguos` y `[1] Crear un
  profile nuevo`; los profiles existentes empiezan en `[2]`.
- Pega el bloque `export AWS_ACCESS_KEY_ID=...` (Access Key, Secret Key y
  Session Token) y presiona Enter dos veces. El script extrae las claves,
  guarda el profile (región `us-east-1`, salida `json`) y verifica la conexión
  con `aws sts get-caller-identity`.
- Al terminar puedes salir o registrar otro profile.
- Para borrar, usa `[0]`: acepta números separados por coma, `todos` (menos
  `default`) o `todo-absoluto`, y ofrece un backup previo.

## Resultado de la instalación

- **Portátil:** `dist\AWSProfileManager.exe`.
- **Instalador:** `dist\installer\AWSProfileManager-Setup.exe`. Instala para el
  usuario actual en `%LOCALAPPDATA%\Programs\AWS Profile Manager`, crea acceso
  directo en el menú Inicio y ofrece uno en el Escritorio.

## Notas de la interfaz

- La caja de **Credenciales rápidas** se agranda arrastrando la barra gris
  inferior.
- Al extraer credenciales, el texto pegado se limpia para no dejarlas visibles.
