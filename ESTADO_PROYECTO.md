\# ESTADO PROYECTO - LEXVIEW PRO LIMPIO



\## Base utilizada



Commit base:



5b2e3c53



Fix localidades interior + sincronizacion parcial inteligente



\---



\## Reconstrucción limpia



Repositorio:



D:\\LexViewPro-LIMPIO



Estado Git actual:



ca9c21b Fix enviar tipo y localidad al completar historial



d78ccf9 Fix stale table al completar historial



d64e03d Fix modal solo parciales actualizados



83a0b48 Fix descarga PDF int o tuple



6b35e4b Base limpia desde 5b2e3c53



\---



\## Fixes reconstruidos y verificados



\### 1. Descarga PDF



Problema:



TypeError: cannot unpack non-iterable int object



Estado:



RESUELTO



Commit:



83a0b48



\---



\### 2. Modal de parciales



Problema:



Mostraba todos los expedientes parciales de la base.



Estado:



RESUELTO



Commit:



d64e03d



\---



\### 3. Tipo y localidad



Problema:



Completar historial asumía Capital.



Estado:



RESUELTO



Commit:



ca9c21b



Verificado con localidades del interior.



\---



\### 4. StaleElementReferenceException



Problema:



Tabla obsoleta durante completar historial.



Estado:



RESUELTO



Commit:



d78ccf9



\---



\## Pendientes inmediatos



\* Instalar qrcode\[pil] en entorno limpio.

\* Actualizar requirements.txt.

\* Crear commit de dependencia QR.



\---



\## Próximas mejoras



1\. Vista preliminar PDF en cédulas.

2\. Backup / Restaurar.

3\. Compartir visor por WhatsApp.

4\. Carga masiva de escritos a FORUM.

5\. Portal cliente.

6\. Aplicación móvil.



\---



\## Ideas futuras



\* Línea de tiempo del expediente.

\* Resumen automático de actuaciones.

\* Detección automática de vencimientos.

\* Alertas inteligentes.

\* Portal online para clientes.

\* Compartir visor con marca de agua del estudio.



\---



\## HITO CONFIRMADO - AUTO UPDATE



Fecha: 09/06/2026



Se validó correctamente el sistema de actualización automática.



Prueba realizada:



\- Instalación inicial: 2.3.2

\- Versión remota publicada: 2.3.3

\- Repo GitHub: https://github.com/Rengardelito/LexView-Pro

\- Release usado: v2.3.3

\- ZIP: lexview-update-2.3.3.zip

\- SHA256: 938d14ef0c028e352142a9daa33c9369d6e50454cbf25bb5165c9fb28c2f1970

\- VPS /api/version apuntando al repo nuevo LexView-Pro

\- Resultado: LexView detectó la actualización, descargó el ZIP, aplicó el update y abrió correctamente.



Estado:



AUTO-UPDATE FUNCIONANDO END-TO-END.

# ESTADO ACTUAL DEL PROYECTO

## Versión estable vigente

**LEXVIEWPRO v2.3.6**

Estado: **STABLE RELEASE**

Fecha: 15/06/2026

Commit estable:

`cb7c7d9`

Tag:

`v2.3.6`

---

## Funcionalidades validadas

* Importación por lista
* Importación por Excel
* Clasificación automática Capital / Interior
* Detección de localidad
* Actualización de notificaciones
* Sincronización inteligente
* Sincronización por cantidad (5 / 10 / Todas)
* Modal de sincronización por camada
* Visor PDF
* Auditoría
* Cédulas
* Auto Update
* Licencias
* Grace period offline (10 días)
* Gestión de matrículas
* Selector de matrícula en actualización de notificaciones

---

## Cambios incorporados en v2.3.6

### Licencias

* Validación offline por 10 días.
* Preparación para planes Profesional / Estudio.

### Localidades

* Corrección Curuzú Cuatiá.
* Corrección búsquedas por localidad interior.
* Corrección transferencia de localidad entre clasificación y sincronización.

### Sincronización

* Corrección modal persistente.
* Corrección camada importada.
* Corrección selección de expedientes.
* Corrección sincronización interior.

### Matrículas

* Pantalla Matrículas Forum.
* Matrícula principal protegida.
* Matrículas adicionales según licencia.
* Integración con Actualizar Notificaciones.

---

## Punto de retorno estable

Si una versión futura presenta problemas, volver a:

Tag: `v2.3.6`

Commit: `cb7c7d9`
