; comun.nsh: piezas compartidas por el instalador (CidIA.nsi) y el lanzador (lanzador.nsi).
;
; Rutas de CidIA en el equipo (todas por usuario, sin permisos de administrador):
;   $LOCALAPPDATA\Programs\CidIA          instalación (app base, plugin, plantillas, lanzador)
;   $LOCALAPPDATA\CidIA\datos             DSH_HOME: perfil, capa home, .env, conversaciones
;   $LOCALAPPDATA\CidIA\navegador         datos del navegador de la app (--user-data-dir)

!include LogicLib.nsh
!include FileFunc.nsh
!include WordFunc.nsh
!include TextFunc.nsh

; Las estructuras de Windows que se montan con System::Call (STARTUPINFOW, PROPVARIANT) están
; escritas para 32 bits: el makensis portable de construir.ps1 genera ejecutables x86.
!if ${NSIS_PTR_SIZE} > 4
  !error "comun.nsh: compila con el makensis x86 (las estructuras de System::Call son de 32 bits)"
!endif

!define CIDIA_CLAVE "Software\CidIA"
!define CIDIA_CLAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\CidIA"
!define CIDIA_CLAVE_PROTOCOLO "Software\Classes\dsh\shell\open\command"
; Ejecutable de la app base en app\: construir.ps1 lo renombra y le pone el icono y los datos de
; versión de CidIA (rcedit). Las instalaciones anteriores lo tenían con su nombre original.
!define CIDIA_EXE_APP "CidIA.exe"
!define CIDIA_EXE_APP_ANTERIOR "DeepSeek Harness.exe"
; Ejecutable de la DeepSeek Harness del usuario (si la tiene), para devolverle el protocolo dsh://.
!define CIDIA_EXE_DSH "DeepSeek Harness.exe"
; AppUserModelID de CidIA: el lanzador abre la app con él y los accesos directos lo llevan, así la
; barra de tareas muestra la ventana con el acceso directo de CidIA (icono, nombre, anclar) y no
; la agrupa con DeepSeek Harness (com.deepseek.dsh).
!define CIDIA_AUMID "CidIA.Escritorio"
; Datos de versión de los ejecutables de CidIA (lanzador, instalador y app\CidIA.exe; construir.ps1
; lee estas dos líneas para el de la app). Los avisos de licencias van en textos\licencia.txt.
!define CIDIA_EMPRESA "Equipo CidIA"
!define CIDIA_COPYRIGHT "© 2026 Equipo CidIA. Incluye software de código abierto (avisos en textos\licencia.txt)."
!define CIDIA_DATOS "$LOCALAPPDATA\CidIA\datos"
!define CIDIA_NAVEGADOR "$LOCALAPPDATA\CidIA\navegador"
!define CIDIA_ENLACE_PLUGIN "$LOCALAPPDATA\CidIA\datos\profiles\desktop\node_modules\cidia"

; ---------------------------------------------------------------------------------------------
; Escritura de texto en UTF-8. FileWrite de NSIS convierte a la página de códigos del sistema;
; los ficheros de configuración de la app se leen como UTF-8 (rutas con tildes, comentarios en
; castellano), así que se convierte con WideCharToMultiByte y se escribe con WriteFile sobre el
; manejador que devuelve FileOpen.
;   $R8 = manejador (FileOpen ... w)   $R9 = texto
!macro CIDIA_DEFINIR_UTF8 PREFIJO
Function ${PREFIJO}EscribirUTF8
  Push $0
  Push $1
  Push $2
  System::Call 'kernel32::WideCharToMultiByte(i 65001, i 0, w R9, i -1, p 0, i 0, p 0, p 0) i .r0'
  ${If} $0 > 1
    System::Alloc $0
    Pop $1
    System::Call 'kernel32::WideCharToMultiByte(i 65001, i 0, w R9, i -1, p r1, i r0, p 0, p 0) i .r2'
    IntOp $2 $2 - 1
    System::Call 'kernel32::WriteFile(p R8, p r1, i r2, *i 0, p 0) i .r0'
    System::Free $1
  ${EndIf}
  Pop $2
  Pop $1
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; Enlace del perfil al plugin (junction, no necesita permisos de administrador).
; Si ya existe un enlace se quita solo el enlace (cmd rmdir no sigue junctions); si es una
; carpeta normal se borra con su contenido.
;   $R0 = ruta del enlace
!macro CIDIA_DEFINIR_ENLACES PREFIJO
Function ${PREFIJO}QuitarEnlace
  Push $0
  System::Call 'kernel32::GetFileAttributesW(w R0) i .r0'
  ${If} $0 <> -1
    IntOp $0 $0 & 0x400 ; FILE_ATTRIBUTE_REPARSE_POINT
    ${If} $0 <> 0
      nsExec::Exec '"$SYSDIR\cmd.exe" /d /c rmdir "$R0"'
      Pop $0
    ${Else}
      RMDir /r "$R0"
    ${EndIf}
  ${EndIf}
  Pop $0
FunctionEnd

;   $R0 = ruta del enlace   $R1 = carpeta destino
Function ${PREFIJO}CrearEnlace
  Push $0
  Call ${PREFIJO}QuitarEnlace
  ${GetParent} "$R0" $0
  CreateDirectory "$0"
  nsExec::Exec '"$SYSDIR\cmd.exe" /d /c mklink /J "$R0" "$R1"'
  Pop $0
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; Protocolo dsh://. La app base lo registra a su nombre al arrancar (setAsDefaultProtocolClient).
; En un equipo que también tiene DeepSeek Harness, CidIA no debe quedarse con él: se restaura.
;   $R0 = valor anterior de la orden (vacío si no había)   $R1 = carpeta de la app de CidIA
;   $R2 = "borrar" para quitar el protocolo si no hay valor anterior (desinstalación)
!macro CIDIA_DEFINIR_PROTOCOLO PREFIJO
Function ${PREFIJO}RestaurarProtocolo
  Push $0
  Push $1
  ReadRegStr $0 HKCU "${CIDIA_CLAVE_PROTOCOLO}" ""
  ; ¿Apunta ahora a la app de CidIA?
  ClearErrors
  ${WordFind} "$0" "$R1" "E+1{" $1
  ${If} ${Errors}
    ; No apunta a CidIA: nada que hacer.
  ${ElseIf} "$R0" != ""
  ${AndIf} "$R0" != "$0"
    WriteRegStr HKCU "${CIDIA_CLAVE_PROTOCOLO}" "" "$R0"
  ${ElseIf} "$R0" == ""
  ${AndIf} "$R2" == "borrar"
    DeleteRegKey HKCU "Software\Classes\dsh"
  ${EndIf}
  ClearErrors
  Pop $1
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; AppUserModelID de un acceso directo (propiedad System.AppUserModel.ID del .lnk), con las
; interfaces COM del shell: IShellLinkW -> IPersistFile (Load/Save) e IPropertyStore (SetValue).
; NSIS no tiene una orden para esto. Estructuras para 32 bits (makensis x86).
;   $R0 = ruta del .lnk   $R1 = AppUserModelID   ->   $R2 = "1" si se ha guardado
!macro CIDIA_DEFINIR_AUMID PREFIJO
Function ${PREFIJO}FijarAumid
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  Push $6
  Push $7
  StrCpy $R2 "0"
  System::Call 'ole32::CoInitialize(p 0) i .r7'
  ; CLSID_ShellLink, IID_IShellLinkW
  System::Call 'ole32::CoCreateInstance(g "{00021401-0000-0000-C000-000000000046}", p 0, i 1, g "{000214F9-0000-0000-C000-000000000046}", *p .r1) i .r0'
  ${If} $0 = 0
    ; IUnknown::QueryInterface(IID_IPersistFile)
    System::Call '$1->0(g "{0000010b-0000-0000-C000-000000000046}", *p .r2) i .r0'
    ${If} $0 = 0
      ; IPersistFile::Load(ruta, STGM_READWRITE)
      System::Call '$2->5(w R0, i 2) i .r0'
      ${If} $0 = 0
        ; IUnknown::QueryInterface(IID_IPropertyStore)
        System::Call '$1->0(g "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}", *p .r3) i .r0'
        ${If} $0 = 0
          ; PROPERTYKEY (20 bytes) de System.AppUserModel.ID y PROPVARIANT VT_LPWSTR (31) con el ID.
          System::Call '*(i 0, i 0, i 0, i 0, i 0) p .r4'
          System::Call 'propsys::PSGetPropertyKeyFromName(w "System.AppUserModel.ID", p r4) i .r0'
          System::Call '*(&w130 R1) p .r6'
          System::Call '*(&i2 31, &i2 0, &i2 0, &i2 0, p r6, i 0) p .r5'
          ${If} $0 = 0
            ; IPropertyStore::SetValue y Commit; IPersistFile::Save(NULL, TRUE)
            System::Call '$3->6(p r4, p r5) i .r0'
            ${If} $0 = 0
              System::Call '$3->7() i .r0'
              ${If} $0 = 0
                System::Call '$2->6(p 0, i 1) i .r0'
                ${If} $0 = 0
                  StrCpy $R2 "1"
                ${EndIf}
              ${EndIf}
            ${EndIf}
          ${EndIf}
          System::Free $5
          System::Free $6
          System::Free $4
          System::Call '$3->2()'
        ${EndIf}
      ${EndIf}
      System::Call '$2->2()'
    ${EndIf}
    System::Call '$1->2()'
  ${EndIf}
  ${If} $7 = 0
  ${OrIf} $7 = 1
    System::Call 'ole32::CoUninitialize()'
  ${EndIf}
  Pop $7
  Pop $6
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; ¿Está abierta la copia de la app de CidIA? Un ejecutable en uso no se puede renombrar.
;   $R0 = ruta del ejecutable   ->   $R1 = "1" si está en uso
!macro CIDIA_DEFINIR_EN_USO PREFIJO
Function ${PREFIJO}AppEnUso
  StrCpy $R1 "0"
  ${If} ${FileExists} "$R0"
    ClearErrors
    Rename "$R0" "$R0.comprobacion"
    ${If} ${Errors}
      StrCpy $R1 "1"
    ${Else}
      Rename "$R0.comprobacion" "$R0"
    ${EndIf}
  ${EndIf}
  ClearErrors
FunctionEnd
!macroend
