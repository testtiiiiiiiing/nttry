# Confronto con le funzioni NTLite richieste

Riferimento: elenco fornito dall'utente dalla pagina https://ntlite.com/features/. La pagina non era leggibile dal proxy della macchina; non è stata verificata direttamente. Questo confronto descrive il codice implementato, non certifica parità con NTLite né compatibilità con tutte le versioni Windows. Le operazioni DISM e Windows Setup necessitano di verifica Windows.

| Funzione richiesta | Implementazione in WinImage Studio 2 | Differenze / lavoro ancora necessario |
|---|---|---|
| Image Management: ISO, WIM, ESD, SWM | Importazione ISO; normalizzazione WIM/ESD tramite DISM; SWM tramite wimlib esterno; ricostruzione ISO BIOS/UEFI | GUI centrata sulle ISO; una sola edizione per ISO risultante; nessuna esportazione ESD/SWM del risultato |
| Deployed Install Editing | Non implementato | Il motore modifica solo copie offline; non fa manutenzione del Windows in esecuzione |
| Host Refresh Wizard | Non implementato | Nessun wizard di reinstallazione/upgrade del sistema corrente |
| Updates | Coda CAB/MSU e integrazione DISM offline | Ordine e compatibilità scelti dall'utente; nessuna risoluzione automatica delle dipendenze |
| Update Performance | Download paralleli e cache persistente verificata | Non include estrazione parallela degli aggiornamenti o cache di componenti estratti |
| Updates Downloader | Downloader da manifest Microsoft con SHA-256 | Non ricerca automaticamente cumulative/component updates dal Catalog |
| Secure Boot Readiness | Non implementato | Nessuna verifica firmware o migrazione UEFI CA 2023 |
| Cleanup & Optimization | DISM StartComponentCleanup ed esportazione finale WIM compressa | Nessuna promessa sulla riduzione ottenuta; dipende da immagine e stato dei pacchetti |
| Drivers | Integrazione cartelle INF e rimozione driver OEM | Nessuna integrazione non firmata; compatibilità decisa dall'utente |
| Hardware Targeting | Esportazione driver del PC Windows attuale e accodamento nell'immagine | Nessun rilevamento automatico di hardware remoto o controllo di tutte le dipendenze |
| Registry | Valori REG_DWORD/REG_SZ in SOFTWARE, SYSTEM e profilo Default offline | Non importa automaticamente file REG arbitrari; supporto limitato ai tipi esposti |
| Power Plan | Importazione file POW e attivazione tramite SetupComplete | Nessun editor dei parametri o gestione del piano energetico del sistema corrente |
| Post-Setup (add) | EXE/MSI/CMD/BAT con argomenti e payload nell'immagine | Richiede installer silenziosi compatibili con esecuzione SYSTEM |
| Install Updates Wizard | Coda aggiornamenti nella GUI, applicazione alla copia WIM | Nessun wizard per installare aggiornamenti sul sistema corrente |
| Components | Rimozioni DISM: pacchetti, Appx provisionate, capabilities e payload features | Non replica la rimozione chirurgica proprietaria di NTLite; le protezioni non sono una matrice completa di compatibilità |
| Remove Reinstalls | Non implementato | StartComponentCleanup non equivale alla gestione proprietaria dei componenti reinstallati |
| Scheduled Tasks | Comandi enable/disable/delete tramite schtasks in post-setup | Non modifica direttamente il database di attività nell'immagine offline |
| Settings | Criteri consumer/telemetria, preferenze Explorer/ricerca e valori registro personalizzati | Nessun catalogo equivalente alle migliaia di impostazioni NTLite; effetti dipendenti dall'edizione |
| Features | Inventario, abilitazione, disabilitazione, rimozione payload e capabilities | Funzionalità con sorgenti aggiuntive possono fallire; nessun recupero automatico dal web |
| Services | Configurazione Start nel ControlSet di avvio offline | Alcuni servizi essenziali sono protetti nel selettore; nessuna gestione completa delle dipendenze |
| Unattended Setup | Generatore lingua/nome/fuso orario/EULA e importazione XML esterno | Generatore lascia OOBE/account interattivi; automazione completa richiede un answer file esterno valido |
| Disk Partitioning | Generatore distruttivo GPT/UEFI: EFI, MSR, Windows; disco esplicito e conferme | Nessun editor di layout arbitrari, BIOS/MBR o Recovery dedicata; XML esterno per altri layout |
| Post-Setup (run) | SetupComplete durante installazione della ISO | Non eseguito ora né verificato su Windows; limitazioni OEM e installer interattivi |
| Image Tasks | CLI batch su più indici, una ISO per edizione | Non applica lo stesso piano a tutte le edizioni mantenendole nella medesima ISO |
| Command-Line Automation | inspect/run/resume/validate-preset/download-updates con codici di uscita | Non è compatibile con sintassi o preset NTLite |

## Validazione disponibile

- Test automatici della logica con DISM, oscdimg e rete simulati.
- Apertura GUI, schede, coda e round-trip del preset in display virtuale Linux.
- Conversione SWM/WIM reale con wimlib 1.14.4, verifica integrità e confronto dei dati ripristinati.
- Build Windows automatizzata configurata in GitHub Actions; l'esito deve essere controllato dopo la pubblicazione.
- DISM reale, installazione Windows, Secure Boot, BIOS/UEFI, unattended e post-setup: **non verificati nell'ambiente Linux**.
