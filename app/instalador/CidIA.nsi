; CidIA.nsi: instalador de CidIA para Windows (CidIA-Setup.exe).
;
; Instalación por usuario, sin permisos de administrador, en $LOCALAPPDATA\Programs\CidIA:
;   app\             app base (DeepSeek Harness 0.2.0-rc.2, extraída del instalador oficial,
;                    sin app-update.yml para que no se actualice sola)
;   plugins\cidia\   plugin CidIA (interfaz, sesión, marca e idioma)
;   plantillas\      perfil y capa home de referencia (el lanzador los usa para repararse)
;   CidIA.exe        lanzador (fija DSH_HOME y abre la app con su propio perfil)
; y prepara los datos en $LOCALAPPDATA\CidIA\datos (DSH_HOME) con la dirección del servidor.
;
; Lo genera construir.ps1, que pasa con /D: VERSION, CARGA (carpeta de carga), SERVIDOR,
; SALIDA y PLANTILLAS (include generado a partir de app\perfil).
;
; Uso sin ventanas:  CidIA-Setup.exe /S /SERVIDOR=http://servidor-cidia:18700
;                   (código 2: CidIA está abierta; 3: la carpeta /D= tiene otros ficheros)
; Desinstalar:       "Desinstalar CidIA.exe" [/S] [/BORRARDATOS]

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!ifndef VERSION
  !define VERSION "0.1.0"
!endif
!ifndef VERSION_WIN
  !define VERSION_WIN "0.1.0.0"
!endif
!ifndef SERVIDOR
  !define SERVIDOR "http://127.0.0.1:18700"
!endif
!ifndef CARGA
  !error "Falta /DCARGA=<carpeta de carga> (lo pasa construir.ps1)"
!endif
!ifndef SALIDA
  !define SALIDA "salida\CidIA-Setup.exe"
!endif
!ifndef PLANTILLAS
  !define PLANTILLAS "${CARGA}\plantillas.nsh"
!endif

!include MUI2.nsh
!include nsDialogs.nsh
!include comun.nsh

Name "CidIA"
Caption "Instalación de CidIA"
UninstallCaption "Desinstalación de CidIA"
BrandingText "CidIA ${VERSION}"
OutFile "${SALIDA}"
InstallDir "$LOCALAPPDATA\Programs\CidIA"
InstallDirRegKey HKCU "${CIDIA_CLAVE}" "Instalacion"
RequestExecutionLevel user
ShowInstDetails hide
ShowUninstDetails hide

VIProductVersion "${VERSION_WIN}"
VIAddVersionKey /LANG=0 "ProductName" "CidIA"
VIAddVersionKey /LANG=0 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "FileDescription" "Instalador de CidIA, copiloto de conocimiento industrial"
VIAddVersionKey /LANG=0 "LegalCopyright" "CidIA. Incluye DeepSeek Harness (licencia MIT)."

Var Servidor
Var RutaPlugin
Var Dialogo
Var CampoServidor
Var EtiquetaEstado
Var CasillaDatos
Var BorrarDatos

; --------------------------------------------------------------------------------- páginas
!define MUI_ICON "${CARGA}\marca\cidia.ico"
!define MUI_UNICON "${CARGA}\marca\cidia.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${CARGA}\marca\instalador-bienvenida.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${CARGA}\marca\instalador-bienvenida.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${CARGA}\marca\instalador-cabecera.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "${CARGA}\marca\instalador-cabecera.bmp"
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "¿Seguro que quieres cancelar la instalación de CidIA?"

!define MUI_WELCOMEPAGE_TITLE "Te damos la bienvenida a CidIA"
!define MUI_WELCOMEPAGE_TEXT "CidIA es el copiloto de conocimiento industrial de tu empresa: captura cómo se hacen las tareas, te acompaña en el puesto, te forma y registra tu progreso.$\r$\n$\r$\nEste asistente instalará CidIA ${VERSION} para tu usuario de Windows. No necesita permisos de administrador.$\r$\n$\r$\nPulsa Siguiente para continuar."
!insertmacro MUI_PAGE_WELCOME

!define MUI_LICENSEPAGE_TEXT_TOP "Lee las condiciones y los avisos de licencias de CidIA."
!define MUI_LICENSEPAGE_BUTTON "Acepto"
!insertmacro MUI_PAGE_LICENSE "${CARGA}\textos\licencia.txt"

Page custom PaginaServidor PaginaServidorSalir

!define MUI_DIRECTORYPAGE_TEXT_TOP "CidIA se instalará en esta carpeta, que debe estar vacía o ser la de una instalación anterior de CidIA. Tus datos se guardan aparte, en $LOCALAPPDATA\CidIA."
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CarpetaSalir
!insertmacro MUI_PAGE_DIRECTORY

!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "Instalación terminada"
!define MUI_INSTFILESPAGE_FINISHHEADER_SUBTEXT "CidIA está lista para usarse."
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "CidIA está instalada"
!define MUI_FINISHPAGE_TEXT "Encontrarás CidIA en el escritorio y en el menú Inicio.$\r$\n$\r$\nServidor configurado:$\r$\n$Servidor"
!define MUI_FINISHPAGE_RUN "$INSTDIR\CidIA.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir CidIA ahora"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.PaginaDatos un.PaginaDatosSalir
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"

; Funciones compartidas (instalador y desinstalador llevan su propia copia).
!insertmacro CIDIA_DEFINIR_UTF8 ""
!insertmacro CIDIA_DEFINIR_ENLACES ""
!insertmacro CIDIA_DEFINIR_ENLACES "un."
!insertmacro CIDIA_DEFINIR_PROTOCOLO "un."
!insertmacro CIDIA_DEFINIR_EN_USO ""
!insertmacro CIDIA_DEFINIR_EN_USO "un."
!include "${PLANTILLAS}"

; --------------------------------------------------------------------------------- inicio
Function .onInit
  ; Dirección del servidor: la de la instalación anterior, la del perfil de construcción o la
  ; que llegue por la línea de órdenes (/SERVIDOR=...).
  ReadRegStr $Servidor HKCU "${CIDIA_CLAVE}" "Servidor"
  ${If} $Servidor == ""
    StrCpy $Servidor "${SERVIDOR}"
  ${EndIf}
  ; GetOptions corta el valor en la primera «/» (la de http://): se busca a mano.
  ${GetParameters} $R0
  ClearErrors
  ${WordFind} "$R0" "/SERVIDOR=" "E+1}" $R1
  ${IfNot} ${Errors}
    ${WordReplace} "$R1" '"' "" "+" $R1
    ${WordFind} "$R1" " " "+1{" $R1
    StrCpy $Servidor "$R1"
  ${EndIf}
  ClearErrors
  Push $Servidor
  Call NormalizarServidor
  Pop $Servidor
FunctionEnd

; ${Trim}: quita espacios y tabuladores al principio y al final.
!define Trim "!insertmacro CIDIA_TRIM"
!macro CIDIA_TRIM RESULTADO TEXTO
  Push "${TEXTO}"
  Call RecortarTexto
  Pop "${RESULTADO}"
!macroend
Function RecortarTexto
  Exch $0
  Push $1
  ${Do}
    StrCpy $1 $0 1
    ${If} $1 == " "
    ${OrIf} $1 == "$\t"
      StrCpy $0 $0 "" 1
    ${Else}
      ${ExitDo}
    ${EndIf}
  ${Loop}
  ${Do}
    StrCpy $1 $0 1 -1
    ${If} $1 == " "
    ${OrIf} $1 == "$\t"
      StrCpy $0 $0 -1
    ${Else}
      ${ExitDo}
    ${EndIf}
  ${Loop}
  Pop $1
  Exch $0
FunctionEnd

; Quita espacios y barras finales; sin esquema se supone http://. Devuelve "" si no vale.
Function NormalizarServidor
  Exch $0
  Push $1
  ${Trim} $0 $0
  ${Do}
    StrCpy $1 $0 1 -1
    ${If} $1 == "/"
      StrCpy $0 $0 -1
    ${Else}
      ${ExitDo}
    ${EndIf}
  ${Loop}
  ; Solo el esquema («http://» sin servidor) no vale.
  ${If} $0 == "http:"
  ${OrIf} $0 == "https:"
    StrCpy $0 ""
  ${EndIf}
  ${If} $0 != ""
    StrCpy $1 $0 7
    ${If} $1 != "http://"
      StrCpy $1 $0 8
      ${If} $1 != "https://"
        StrCpy $0 "http://$0"
      ${EndIf}
    ${EndIf}
    ; Sin espacios, comillas ni saltos de línea: va a ficheros de configuración.
    ${WordFind} "$0" " " "E#" $1
    ${IfNot} ${Errors}
      StrCpy $0 ""
    ${EndIf}
    ClearErrors
    ${WordFind} "$0" '"' "E#" $1
    ${IfNot} ${Errors}
      StrCpy $0 ""
    ${EndIf}
    ClearErrors
    ${WordFind} "$0" "'" "E#" $1
    ${IfNot} ${Errors}
      StrCpy $0 ""
    ${EndIf}
    ClearErrors
    ; Ni barras invertidas (rompen la capa home: YAML entre comillas dobles y JavaScript).
    ${WordFind} "$0" "\" "E#" $1
    ${IfNot} ${Errors}
      StrCpy $0 ""
    ${EndIf}
    ClearErrors
    ; Y con algo detrás del esquema que pueda ser un servidor.
    StrCpy $1 $0 8
    ${If} $1 == "https://"
      StrCpy $1 $0 1 8
    ${Else}
      StrCpy $1 $0 1 7
    ${EndIf}
    ${If} $1 == ""
    ${OrIf} $1 == "/"
    ${OrIf} $1 == ":"
      StrCpy $0 ""
    ${EndIf}
  ${EndIf}
  Pop $1
  Exch $0
FunctionEnd

; --------------------------------------------------------------------------------- carpeta
; El instalador sustituye app\ y plugins\cidia\, y el desinstalador borra app\, plugins\,
; plantillas\ y textos\: en una carpeta con otros ficheros podrían ser de la persona. Solo se
; admite una carpeta que no existe, vacía o con una instalación anterior de CidIA.
;   -> $R1 = "1" si se puede instalar en $INSTDIR
Function CarpetaAdmitida
  Push $0
  StrCpy $R1 "1"
  ${DirState} "$INSTDIR" $0
  ${If} $0 == 1
  ${AndIfNot} ${FileExists} "$INSTDIR\CidIA.exe"
  ${AndIfNot} ${FileExists} "$INSTDIR\Desinstalar CidIA.exe"
    StrCpy $R1 "0"
  ${EndIf}
  Pop $0
FunctionEnd

Function CarpetaSalir
  Call CarpetaAdmitida
  ${If} $R1 != "1"
    MessageBox MB_ICONEXCLAMATION|MB_OK "La carpeta $INSTDIR ya tiene otros ficheros.$\r$\n$\r$\nElige una carpeta vacía o la de una instalación anterior de CidIA, por ejemplo $LOCALAPPDATA\Programs\CidIA"
    Abort
  ${EndIf}
FunctionEnd

; --------------------------------------------------------------------------------- servidor
Function PaginaServidor
  !insertmacro MUI_HEADER_TEXT "Servidor CidIA de la empresa" "Dirección del servidor al que se conectará la app."
  nsDialogs::Create 1018
  Pop $Dialogo
  ${If} $Dialogo == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 30u "Escribe la dirección del servidor CidIA de tu empresa. Te la da el equipo de sistemas y suele tener esta forma: http://servidor-cidia:18700"
  Pop $0
  ${NSD_CreateText} 0 34u 100% 13u "$Servidor"
  Pop $CampoServidor
  ${NSD_CreateButton} 0 54u 92u 15u "Comprobar conexión"
  Pop $0
  ${NSD_OnClick} $0 ComprobarServidor
  ${NSD_CreateLabel} 100u 57u 200u 30u ""
  Pop $EtiquetaEstado
  ${NSD_CreateLabel} 0 104u 100% 30u "Podrás cambiarla más adelante en el fichero .env de $LOCALAPPDATA\CidIA\datos (y reiniciando CidIA), o volviendo a ejecutar este instalador."
  Pop $0
  SetCtlColors $0 808080 transparent
  nsDialogs::Show
FunctionEnd

Function ComprobarServidor
  ${NSD_GetText} $CampoServidor $0
  Push $0
  Call NormalizarServidor
  Pop $0
  ${If} $0 == ""
    ${NSD_SetText} $EtiquetaEstado "La dirección no es válida."
    Return
  ${EndIf}
  ${NSD_SetText} $EtiquetaEstado "Comprobando…"
  ; PowerShell solo para esta comprobación opcional. Salida en ASCII para no depender de la
  ; página de códigos de la consola.
  nsExec::ExecToStack `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try { $$i = Invoke-RestMethod -UseBasicParsing -TimeoutSec 6 -Uri '$0/api/sistema/info'; if ($$i.producto -ne 'CidIA') { 'NOCIDIA' } else { 'OK|' + (($$i.servidor + ' / ' + $$i.empresa).Normalize([Text.NormalizationForm]::FormD) -replace '[^\x20-\x7E]', '') } } catch { 'ERROR' }"`
  Pop $1
  Pop $2
  ${WordFind} "$2" "$\r" "+1" $2
  StrCpy $3 $2 3
  ${If} $3 == "OK|"
    StrCpy $2 $2 "" 3
    ${NSD_SetText} $EtiquetaEstado "Conexión correcta: $2"
  ${ElseIf} $2 == "NOCIDIA"
    ${NSD_SetText} $EtiquetaEstado "Responde, pero no parece un servidor CidIA."
  ${Else}
    ${NSD_SetText} $EtiquetaEstado "No responde. Revisa la dirección y que el equipo esté en la red de la empresa. Puedes continuar igualmente."
  ${EndIf}
FunctionEnd

Function PaginaServidorSalir
  ${NSD_GetText} $CampoServidor $0
  Push $0
  Call NormalizarServidor
  Pop $0
  ${If} $0 == ""
    MessageBox MB_ICONEXCLAMATION|MB_OK "Escribe una dirección válida, por ejemplo http://servidor-cidia:18700"
    Abort
  ${EndIf}
  StrCpy $Servidor $0
FunctionEnd

; --------------------------------------------------------------------------------- instalación
Section "CidIA" SeccionCidia
  SectionIn RO
  ${If} $Servidor == ""
    StrCpy $Servidor "${SERVIDOR}"
  ${EndIf}

  ; Sin ventanas (/D=) no pasa por la página de la carpeta: se comprueba aquí también.
  Call CarpetaAdmitida
  ${If} $R1 != "1"
    ${If} ${Silent}
      SetErrorLevel 3
    ${Else}
      MessageBox MB_ICONSTOP|MB_OK "No se puede instalar CidIA en $INSTDIR: la carpeta ya tiene otros ficheros."
    ${EndIf}
    Quit
  ${EndIf}

  ; CidIA no puede estar abierta mientras se sustituyen sus ficheros.
  ${Do}
    StrCpy $R0 "$INSTDIR\app\${CIDIA_EXE_APP}"
    Call AppEnUso
    ${If} $R1 == "0"
      ${ExitDo}
    ${EndIf}
    ${If} ${Silent}
      SetErrorLevel 2
      Quit
    ${EndIf}
    MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "CidIA está abierta. Ciérrala (también desde el icono junto al reloj) y pulsa Reintentar." IDRETRY reintentar_instalar
    Quit
    reintentar_instalar:
  ${Loop}

  ; App base: se sustituye entera para no dejar ficheros de una versión anterior.
  DetailPrint "Instalando la app base…"
  RMDir /r "$INSTDIR\app"
  SetOutPath "$INSTDIR\app"
  File /r /x .cidia-origen "${CARGA}\app\*.*"

  DetailPrint "Instalando el plugin CidIA…"
  RMDir /r "$INSTDIR\plugins\cidia"
  SetOutPath "$INSTDIR\plugins\cidia"
  File /r "${CARGA}\plugin\cidia\*.*"

  SetOutPath "$INSTDIR\plantillas"
  File /r "${CARGA}\perfil\*.*"
  SetOutPath "$INSTDIR\textos"
  File /r "${CARGA}\textos\*.*"
  SetOutPath "$INSTDIR"
  File "${CARGA}\CidIA.exe"
  File "${CARGA}\marca\cidia.ico"

  ; Datos de CidIA (DSH_HOME): capa home, .env y perfil de escritorio con el bundle cidia.
  DetailPrint "Preparando los datos de CidIA…"
  StrCpy $RutaPlugin "$INSTDIR\plugins\cidia"
  ${WordReplace} "$RutaPlugin" "\" "/" "+" $RutaPlugin
  CreateDirectory "${CIDIA_DATOS}\profiles\desktop\node_modules"
  !insertmacro CIDIA_ESCRIBIR_ENV "${CIDIA_DATOS}\.env"
  !insertmacro CIDIA_ESCRIBIR_PATCH_HOME "${CIDIA_DATOS}\cordis.patch.yml"
  !insertmacro CIDIA_ESCRIBIR_PAQUETE_PERFIL "${CIDIA_DATOS}\profiles\desktop\package.json"
  !insertmacro CIDIA_ESCRIBIR_PNPM "${CIDIA_DATOS}\profiles\desktop\pnpm-workspace.yaml"
  ; La capa de usuario del perfil es de la persona: solo se crea si no existe.
  ${IfNot} ${FileExists} "${CIDIA_DATOS}\profiles\desktop\cordis.patch.yml"
    !insertmacro CIDIA_ESCRIBIR_PATCH_USUARIO "${CIDIA_DATOS}\profiles\desktop\cordis.patch.yml"
  ${EndIf}
  StrCpy $R0 "${CIDIA_ENLACE_PLUGIN}"
  StrCpy $R1 "$INSTDIR\plugins\cidia"
  Call CrearEnlace
  ${IfNot} ${FileExists} "${CIDIA_ENLACE_PLUGIN}\package.json"
    DetailPrint "No se pudo enlazar el plugin CidIA en el perfil."
    ${IfNot} ${Silent}
      MessageBox MB_ICONEXCLAMATION|MB_OK "No se pudo enlazar el plugin CidIA en el perfil de la app. El lanzador lo intentará de nuevo al abrir CidIA."
    ${EndIf}
  ${EndIf}

  ; Accesos directos (solo para este usuario).
  SetShellVarContext current
  CreateShortcut "$SMPROGRAMS\CidIA.lnk" "$INSTDIR\CidIA.exe" "" "$INSTDIR\cidia.ico" 0 SW_SHOWNORMAL "" "CidIA, copiloto de conocimiento industrial"
  CreateShortcut "$DESKTOP\CidIA.lnk" "$INSTDIR\CidIA.exe" "" "$INSTDIR\cidia.ico" 0 SW_SHOWNORMAL "" "CidIA, copiloto de conocimiento industrial"

  ; Registro: configuración y entrada en Aplicaciones instaladas.
  WriteRegStr HKCU "${CIDIA_CLAVE}" "Instalacion" "$INSTDIR"
  WriteRegStr HKCU "${CIDIA_CLAVE}" "Version" "${VERSION}"
  WriteRegStr HKCU "${CIDIA_CLAVE}" "Servidor" "$Servidor"
  WriteRegStr HKCU "${CIDIA_CLAVE}" "Datos" "${CIDIA_DATOS}"
  WriteUninstaller "$INSTDIR\Desinstalar CidIA.exe"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "DisplayName" "CidIA"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "Publisher" "CidIA"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "DisplayIcon" "$INSTDIR\cidia.ico"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "UninstallString" '"$INSTDIR\Desinstalar CidIA.exe"'
  WriteRegStr HKCU "${CIDIA_CLAVE_DESINSTALAR}" "QuietUninstallString" '"$INSTDIR\Desinstalar CidIA.exe" /S'
  WriteRegDWORD HKCU "${CIDIA_CLAVE_DESINSTALAR}" "NoModify" 1
  WriteRegDWORD HKCU "${CIDIA_CLAVE_DESINSTALAR}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${CIDIA_CLAVE_DESINSTALAR}" "EstimatedSize" "$0"
  DetailPrint "CidIA instalada. Servidor: $Servidor"
SectionEnd

; --------------------------------------------------------------------------------- desinstalación
Function un.onInit
  StrCpy $BorrarDatos "0"
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} "$R0" "/BORRARDATOS" $R1
  ${IfNot} ${Errors}
    StrCpy $BorrarDatos "1"
  ${EndIf}
  ClearErrors
FunctionEnd

Function un.PaginaDatos
  !insertmacro MUI_HEADER_TEXT "Tus datos de CidIA" "Elige si quieres conservarlos."
  nsDialogs::Create 1018
  Pop $Dialogo
  ${NSD_CreateLabel} 0 0 100% 40u "Se quitará la app CidIA de este equipo. Tus conversaciones, ajustes y la caché de la app están en $LOCALAPPDATA\CidIA. Si los conservas, se usarán al volver a instalar CidIA."
  Pop $0
  ${NSD_CreateCheckbox} 0 48u 100% 12u "Borrar también mis datos de CidIA en este equipo"
  Pop $CasillaDatos
  ${If} $BorrarDatos == "1"
    ${NSD_Check} $CasillaDatos
  ${EndIf}
  ${NSD_CreateLabel} 0 66u 100% 24u "Tu progreso, tu formación y tus aportaciones están en el servidor de la empresa y no se borran."
  Pop $0
  SetCtlColors $0 808080 transparent
  nsDialogs::Show
FunctionEnd

Function un.PaginaDatosSalir
  ${NSD_GetState} $CasillaDatos $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $BorrarDatos "1"
  ${Else}
    StrCpy $BorrarDatos "0"
  ${EndIf}
FunctionEnd

Section "Uninstall"
  ${Do}
    StrCpy $R0 "$INSTDIR\app\${CIDIA_EXE_APP}"
    Call un.AppEnUso
    ${If} $R1 == "0"
      ${ExitDo}
    ${EndIf}
    ${If} ${Silent}
      SetErrorLevel 2
      Quit
    ${EndIf}
    MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "CidIA está abierta. Ciérrala (también desde el icono junto al reloj) y pulsa Reintentar." IDRETRY reintentar_desinstalar
    Quit
    reintentar_desinstalar:
  ${Loop}

  ; El protocolo dsh:// vuelve a DeepSeek Harness si está instalada; si no, se quita.
  StrCpy $R1 "$INSTDIR\app"
  ${If} ${FileExists} "$LOCALAPPDATA\Programs\DeepSeek Harness\${CIDIA_EXE_APP}"
    StrCpy $R0 '"$LOCALAPPDATA\Programs\DeepSeek Harness\${CIDIA_EXE_APP}" "%1"'
    StrCpy $R2 ""
  ${Else}
    StrCpy $R0 ""
    StrCpy $R2 "borrar"
  ${EndIf}
  Call un.RestaurarProtocolo

  SetShellVarContext current
  Delete "$SMPROGRAMS\CidIA.lnk"
  Delete "$DESKTOP\CidIA.lnk"

  ; Primero el enlace del perfil (nunca se borra a través de él), luego la instalación.
  StrCpy $R0 "${CIDIA_ENLACE_PLUGIN}"
  Call un.QuitarEnlace
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\plugins"
  RMDir /r "$INSTDIR\plantillas"
  RMDir /r "$INSTDIR\textos"
  Delete "$INSTDIR\CidIA.exe"
  Delete "$INSTDIR\cidia.ico"
  Delete "$INSTDIR\Desinstalar CidIA.exe"
  RMDir "$INSTDIR"

  ${If} $BorrarDatos == "1"
    DetailPrint "Borrando los datos de CidIA…"
    ; rmdir /s no atraviesa enlaces: borra los enlaces, no lo que hay detrás.
    nsExec::Exec '"$SYSDIR\cmd.exe" /d /c rmdir /s /q "$LOCALAPPDATA\CidIA"'
    Pop $0
  ${EndIf}

  DeleteRegKey HKCU "${CIDIA_CLAVE_DESINSTALAR}"
  DeleteRegKey HKCU "${CIDIA_CLAVE}"
SectionEnd
