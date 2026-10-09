# WinImage Studio

Applicazione desktop originale per la manutenzione offline di immagini Windows tramite DISM. È una prima versione, non una replica completa di NTLite e non è affiliata al suo produttore.

## Requisiti e avvio

- Windows 10/11 a 64 bit e Python 3.11 o superiore a 64 bit, con Tcl/Tk e Python Launcher (installer ufficiale Python).
- Privilegi amministratore per DISM e montaggio ISO.
- Windows ADK, componente **Deployment Tools**, solo per ricostruire ISO con `oscdimg.exe`.
- Immagini Windows e driver compatibili, ottenuti da fonti autorizzate. Usare una versione di DISM compatibile con l’immagine.

Aprire PowerShell **come amministratore**, entrare nella cartella del progetto ed eseguire:

```powershell
py -3 -m winimage
```

In alternativa avviare `start.bat` da un terminale amministratore. Non ci sono pacchetti Python esterni da installare.

## Flusso di lavoro

1. Selezionare WIM/ESD e premere **Mostra edizioni** per identificare l’indice.
2. **Esporta copia WIM** crea un nuovo file per lavorare senza modificare l’originale e converte un’edizione ESD in WIM.
3. Selezionare la copia, il suo indice (normalmente 1 dopo l’esportazione di una singola edizione) e una cartella vuota; premere **Monta WIM**.
4. Integrare cartelle di driver INF firmati e pacchetti CAB/MSU compatibili. Consultare gli elenchi DISM prima di abilitare/disabilitare funzionalità o rimuovere pacchetti per identità completa.
5. **Salva e smonta** applica le modifiche al WIM selezionato; **Scarta e smonta** le annulla. Entrambe chiedono conferma.
6. Per una ISO, usare **Estrai ISO** indicando una nuova cartella. Modificare una copia di `sources/install.wim`, quindi sostituirlo nella cartella del supporto dopo aver smontato l’immagine. Se il supporto usa `install.esd`, esportare l’edizione richiesta in `install.wim` e rimuovere solo l’ESD dalla copia del supporto. Un’esportazione singola mantiene una sola edizione.
7. **Crea ISO BIOS + UEFI** richiede la cartella del supporto completo, `oscdimg.exe` e un nuovo file ISO esterno a quella cartella.

La GUI serializza le operazioni, mostra comandi e output al completamento e impedisce la chiusura mentre un’immagine della sessione è montata. DISM può impiegare diversi minuti. Non terminare forzatamente il processo. I dettagli Microsoft sono anche in `%WINDIR%\Logs\DISM\dism.log`.

Se Windows o l’app si interrompono, verificare da un terminale amministratore `dism /Get-MountedWimInfo` e recuperare l’immagine tramite gli strumenti DISM Microsoft prima di ricominciare. La GUI non adotta automaticamente montaggi di sessioni precedenti.

## Verifica

```powershell
py -3 -m unittest discover -s tests -v
```

I test automatici verificano argomenti, gestione errori e protezioni con DISM simulato. Non dimostrano che una specifica immagine Windows sia installabile. Su Windows verificare esportazione, montaggio, elenco funzionalità, una modifica compatibile e smontaggio prima con scarto e poi con salvataggio, su copie sacrificabili. Verificare la ISO risultante avviandola in una VM isolata sia UEFI sia BIOS prima di usarla su hardware.

## Limiti della prima versione

Non include rimozioni arbitrarie di componenti non supportate da DISM, preset NTLite, installazione automatizzata, modifica del sistema Windows in esecuzione, immagini WIM suddivise, firma o distribuzione di un eseguibile standalone. Alcune funzionalità richiedono sorgenti aggiuntive; DISM ne riporta l’errore. In Linux si possono eseguire i test, ma non effettuare manutenzione DISM o validare l’avvio Windows.
