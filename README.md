# WinImage Studio 3

Editor desktop di **ISO di installazione Windows** con DISM. La nuova interfaccia usa una barra laterale, un catalogo componenti interattivo e un progetto completo: **ISO originale → edizione → personalizzazioni → nuova ISO avviabile**. L'originale non viene modificato e non è necessario sostituire manualmente `install.wim` nella ISO.

Le funzioni richieste sono confrontate, una per una, in [docs/features.md](docs/features.md). Il programma ha codice e interfaccia originali: non è NTLite, non usa il suo motore proprietario e non ha ancora tutte le sue funzioni.

## Download e avvio

Da GitHub: **Code → Download ZIP**, estrarre l'archivio.

- **Da sorgenti:** Windows 10/11, Python **3.11+ a 64 bit**, Tcl/Tk e Python Launcher. Aprire un terminale **come amministratore**, entrare nel progetto ed eseguire `py -3 -m winimage` oppure `start.bat`. Nessuna dipendenza Python esterna per il programma.
- **Eseguibile:** `build-windows.bat` compila `dist\WinImage-Studio.exe` su Windows con PyInstaller. L'eseguibile richiede UAC ed è privo di firma digitale. Il workflow GitHub **Actions → Windows build** esegue test e compilazione; se la build riesce, l'artefatto si chiama **WinImage-Studio-Windows**. Il download degli artefatti Actions può richiedere accesso a GitHub. La compilazione non dimostra la compatibilità di ogni immagine Windows.
- **Creazione ISO:** installare il componente **Deployment Tools** del [Windows ADK](https://learn.microsoft.com/windows-hardware/get-started/adk-install). `oscdimg.exe` viene cercato automaticamente; è possibile indicarlo manualmente.
- **Sorgenti SWM:** indicare `wimlib-imagex.exe` dalla distribuzione Windows ufficiale di [wimlib](https://wimlib.net/), con le relative DLL. Non è necessario per WIM/ESD. Il programma invoca lo strumento esterno, senza distribuirlo.
- Usare DISM compatibile con la versione dell'immagine. Servono almeno **25 GiB** liberi o **4 volte la dimensione ISO**, scegliendo il valore maggiore. Il controllo è preventivo, non garantisce spazio sufficiente per tutti gli aggiornamenti. Il progetto deve risiedere su un volume che supporta file oltre 4 GiB, normalmente NTFS.

## Modifica di una ISO

1. **ISO e progetto:** scegliere l'originale e una **nuova** cartella progetto; premere **Estrai ISO**. Il supporto deve contenere `sources/boot.wim` e una sorgente `install.wim`, `install.esd` oppure `install.swm` con tutti i suoi segmenti.
2. Scegliere l'edizione e **Carica edizione**. Il programma la esporta in una copia WIM e la monta. La ISO risultante conterrà **una sola edizione**, selezionata qui.
3. **Componenti:** il catalogo viene letto automaticamente dopo il montaggio. Filtrare per tipo, cercare un nome oppure premere **Aggiorna elenco**. Le intestazioni ordinano le righe; **Raggruppa per tipo** riunisce funzionalita, app, driver e tipi di pacchetti. **Disabilita** cambia subito lo stato previsto, mentre **Rimuovi** nasconde la riga. Le modifiche restano in attesa fino ad **Applica**. **Stato immagine** mantiene distinto il punto di partenza dalla scelta prevista. Abilita/Disabilita sono disponibili per le funzionalita; gli altri tipi si rimuovono.
4. **Integrazione:** aggiungere driver INF, aggiornamenti CAB/MSU, installer/script post-setup, piani energetici o pulizia componenti. Gli aggiornamenti sono applicati nell'ordine della coda: stabilire dipendenze e compatibilità dalla documentazione Microsoft. I driver di questo PC possono essere esportati e aggiunti alla coda senza modificare il Windows in esecuzione.
5. **Impostazioni:** scegliere criteri o valori di registro offline e modalità di avvio servizi. Le preferenze del profilo Default si applicano ai nuovi utenti. L'effetto dei criteri dipende dall'edizione Windows. Le attività pianificate sono gestite **dopo l'installazione**, tramite `schtasks`, non cancellando direttamente il database offline.
6. **Installazione:** opzionalmente generare `autounattend.xml` o importare un answer file proprio. Il generatore configura lingua, nome e fuso orario; non automatizza account e OOBE. **Il partizionamento GPT/UEFI opzionale cancella il disco esplicitamente indicato quando la ISO viene installata.** Prevede EFI 260 MiB, MSR 16 MiB e Windows nello spazio rimanente, senza partizione Recovery dedicata. Non usarlo per installazioni BIOS/MBR. Il programma richiede una conferma testuale e una seconda conferma prima di applicare il piano. Senza questa opzione, il disco viene scelto interattivamente durante Setup.
7. **Modifiche e ISO:** revisionare/rimuovere/riordinare la coda, salvare eventualmente un preset, quindi **Applica e salva immagine**. Dopo lo smontaggio, scegliere un nuovo file ISO fuori dal progetto e premere **Crea ISO avviabile**. Il programma conserva l'immagine iniziale del supporto nel progetto, esporta un WIM ottimizzato e ricostruisce la ISO con avvio BIOS/UEFI. La ISO finale viene resa disponibile solo dopo il successo di `oscdimg`.

## Catalogo componenti: comportamento dei pulsanti

- **Ordina:** clic sull'intestazione Tipo, Componente, Stato previsto, Stato immagine o Modifica; secondo clic inverte l'ordine. I nomi con numeri usano ordinamento naturale. Con il raggruppamento attivo, le righe sono ordinate entro il rispettivo tipo; disattivarlo per ordinare l'intero elenco.
- **Disabilita:** la riga mostra subito **Disabilitato** e **Disabilitazione in attesa**. Lo stato di partenza resta visibile nella colonna Stato immagine. Non esegue manutenzione del Windows corrente.
- **Rimuovi:** il componente sparisce dall'elenco normale e compare nel piano **Modifiche e ISO**. Il contatore delle rimozioni si aggiorna. Per rivederlo attivare **Mostra rimozioni in attesa**; appare come Rimosso con il contrassegno Rimozione in attesa.
- **Annulla modifica:** selezionare la riga (anche una rimozione mostrata con la casella) e premere Annulla modifica. In alternativa, nella pagina Modifiche e ISO selezionare l'operazione e premere Annulla selezione. La riga torna al suo stato iniziale.
- **Cambia scelta:** una scelta successiva sul medesimo componente sostituisce la precedente. Riabilitare una funzionalita originariamente abilitata annulla la disabilitazione; non accoda comandi opposti.
- **Aggiorna elenco / importa preset:** conserva le modifiche previste. I componenti rimossi restano nascosti anche dopo una nuova lettura. Le identita complete e i metadati sono visibili nei dettagli della selezione.
- **Applica:** le operazioni completate vengono segnate come Applicata e distinte da quelle ancora in attesa. Dopo un errore, solo i passi completati aggiornano lo stato della vista. Il piano iniziato resta bloccato per evitare modifiche durante la ripresa.

Le rimozioni multiple vengono validate insieme: se la selezione comprende un elemento protetto, non viene accodata una parte della selezione. I gruppi sono intestazioni, non componenti modificabili. Il catalogo e basato sugli inventari Windows supportati; non introduce rimozioni proprietarie di NTLite.

Gli installer post-setup vengono inclusi nel WIM ed eseguiti con privilegi SYSTEM da `SetupComplete.cmd` durante l'installazione. Specificare le opzioni silenziose corrette per ogni produttore; MSI usa già `/qn /norestart`. Gli script CMD/BAT possono eseguire comandi arbitrari: includere solo file revisionati. Alcune licenze OEM disabilitano SetupComplete e alcuni installer richiedono un utente interattivo. Verificare questo flusso in VM. Un `SetupComplete.cmd` preesistente non viene sovrascritto.

Un answer file esterno può contenere account, credenziali, comandi e partizionamento. La validazione verifica struttura XML e namespace, **non l'intero schema Windows Setup**. Non salvare credenziali nei preset o nel repository; revisionare il file e considerare che viene copiato nella ISO.

## Aggiornamenti e cache

**Scarica aggiornamenti da manifest** legge un elenco JSON con URL Microsoft e SHA-256 attendibili. Scarica fino a tre file in parallelo, verifica il contenuto, mantiene la cache e accoda i file nell'ordine del manifest. Non è un motore di ricerca automatico del Microsoft Update Catalog e non individua autonomamente gli aggiornamenti adatti all'edizione.

Schema del manifest: `{"version":1,"updates":[{"url":"URL_HTTPS_MICROSOFT","filename":"pacchetto.msu","sha256":"SHA256_ATTESO_DI_64_CARATTERI"}]}`. Sostituire i segnaposto con dati reali; il programma rifiuta un hash assente/non valido, domini esterni, HTTP e download non corrispondenti. Non vengono disabilitate verifica TLS o controllo dei checksum. I download richiedono connettività dal PC Windows ai relativi domini Microsoft.

## Automazione

Da un terminale Windows amministratore:

```powershell
# Controllare un preset; funziona anche su Linux.
py -3 -m winimage.cli validate-preset presets/basic-it.json

# Estrarre una ISO ed elencare le edizioni.
py -3 -m winimage.cli inspect --iso C:\ISO\Windows.iso --project C:\Progetti\Inspect

# Riprendere il progetto estratto, scegliere un'edizione e creare la ISO.
py -3 -m winimage.cli resume --project C:\Progetti\Inspect --index 6 --preset presets/basic-it.json --output C:\ISO\Personalizzata.iso --oscdimg "C:\Percorso\oscdimg.exe" --confirm

# Workflow intero; batch: una ISO separata per ciascun indice.
py -3 -m winimage.cli run --iso C:\ISO\Windows.iso --project C:\Progetti\Batch --indices 1,6 --preset presets/basic-it.json --output C:\ISO\Personalizzata.iso --oscdimg "C:\Percorso\oscdimg.exe" --confirm

# Download con cache e checksum; non richiede amministratore.
py -3 -m winimage.cli download-updates --manifest aggiornamenti.json --cache C:\Cache\Aggiornamenti
```

Per sorgenti SWM aggiungere `--wimlib "C:\Percorso\wimlib-imagex.exe"`. Se il preset contiene un answer file con `WillWipeDisk=true`, è richiesta anche l'opzione `--confirm-wipe-disk`. Il batch produce cartelle e ISO con suffisso dell'indice; non modifica tutte le edizioni nella stessa ISO. Un preset salva percorsi locali ai driver/installer/XML: devono esistere sul PC di esecuzione.

## Errori e ripresa

`project.json`, `applied-preset.json` e `operations.log` conservano stato, piano e output degli strumenti. La GUI non permette di chiudere durante un'operazione o un montaggio attivo. I comandi DISM possono richiedere molti minuti.

Dopo un errore, i passi riusciti vengono registrati e il piano resta bloccato: correggere il problema e riprendere **lo stesso piano**, oppure scartare il montaggio. La GUI carica il preset del progetto alla riapertura. La ripresa verifica directory, file WIM e stato del montaggio DISM. Un errore può comunque aver applicato parte dell'operazione fallita; controllare il registro prima di ritentare. La registrazione non è una transazione con DISM: un arresto improvviso tra comando e salvataggio può richiedere recupero manuale.

Per un montaggio corrotto, usare gli strumenti DISM Microsoft da terminale amministratore (`dism /Get-MountedWimInfo`, eventualmente `/Remount-Image` o smontaggio del **solo** percorso di questo progetto). Non scartare montaggi di altre applicazioni. Se l'estrazione/normalizzazione è incompleta, conservare il registro e ripartire in una nuova cartella. Le risorse del progetto non vengono cancellate automaticamente.

## Verifica e limiti

```powershell
py -3 -m unittest discover -s tests -v
```

Sono verificati 52 test: orchestrazione, errori, preset, XML, catalogo e stati previsti, rimozioni protette, download con rete simulata e 6 test GUI con clic sui pulsanti. Su Linux senza display i 6 test GUI vengono saltati; nell'ambiente di sviluppo sono stati eseguiti con DISPLAY virtuale. Su Windows vengono eseguiti con Tk. Il percorso ISO → modifiche → nuova ISO nei test usa un motore Windows simulato, **non DISM reale**. È stato inoltre verificato il percorso SWM → WIM con wimlib reale su dati di prova e l'apertura della GUI in un display Linux virtuale. Non è stata verificata l'installazione di una ISO Windows né eseguita una compilazione Windows in questa macchina Linux.

Prima di distribuire una ISO: provare su Windows esportazione, montaggio, inventario, una modifica compatibile, commit e ricostruzione, usando una copia sacrificabile. Avviare il risultato in VM UEFI e BIOS; per preset con partizionamento usare una VM UEFI con un disco virtuale vuoto. Verificare anche OOBE e post-setup. Una build `.exe` riuscita non sostituisce questi controlli.

Non sono implementati editing del sistema installato, Host Refresh, migrazione certificati Secure Boot, rilevamento automatico degli aggiornamenti, rimozione chirurgica proprietaria o pulizia automatica delle reinstallazioni. Il confronto dettagliato è in [docs/features.md](docs/features.md).
