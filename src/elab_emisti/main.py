"""
Aggiunge il record 75 a ogni gruppo di iscrizione nel file emi132-RGS.

Struttura record comune (byte 0-based):
  [0:2]   tipo record
  [2:10]  iscrizione (8 byte)
  [10:16] rata (6 byte, yyyymm)
  [16:18] progressivo_emissione (2 byte)

Record 75 generato:
  "75" + iscrizione(8) + rata(6) + progr(2) + 4 importi(8 byte ciascuno) = 50 char

  [18:26] IMPONCORR_AGEV  (8 cifre, es. 00040000 = 400.00 euro)
  [26:34] IRPEFCORR_AGEV  (8 cifre, es. 00006000 =  60.00 euro)
  [34:42] IMPONACC_AGEV   (8 cifre, es. 00040000 = 400.00 euro)
  [42:50] IRPEFACC_AGEV   (8 cifre, es. 00006000 =  60.00 euro)

I 4 importi sono in centesimi (es. 400.00 → "00040000"), zfill a 8 cifre.
Il record viene aggiunto solo se presente nella mappa caricata da Oracle.
"""

import os
import sys
import shutil
import oracledb


QUERY_BULK = """
SELECT T406_ISCRIZIONE
     , T406_EMISSIONE
     , T406_RATA
     , T406_IMPONCORR_AGEV
     , T406_IRPEFCORR_AGEV
     , T406_IMPONACC_AGEV
     , T406_IRPEFACC_AGEV
  FROM e406_cedolino_irpef
     , e083_assegni_emessi
 WHERE T083_RATA_EMISSIONE  = :rataEmissione
   AND T083_PROGR_EMISSIONE = T406_EMISSIONE
   AND T083_ISCRIZIONE      = T406_ISCRIZIONE
   AND T083_RATA            = T406_RATA
   AND t406_emissione  in ({progressivi})
   AND (T406_IRPEFCORR_AGEV <> 0 OR T406_IRPEFACC_AGEV <> 0)
"""


def to_centesimi(valore) -> str:
    """Converte un importo decimale in centesimi, formattato su 8 cifre con zfill."""
    if valore is None:
        return "00000000"
    centesimi = round(float(valore) * 100)
    return str(int(centesimi)).zfill(8)


def build_record75(iscrizione: str, rata: str, progr: str, row) -> str:
    campo1 = to_centesimi(row[0])
    campo2 = to_centesimi(row[1])
    campo3 = to_centesimi(row[2])
    campo4 = to_centesimi(row[3])
    return f"75{iscrizione}{rata}{progr}{campo1}{campo2}{campo3}{campo4}"


def load_mappa(cursor, rata_emissione: str, progressivi: str) -> dict:
    valori_progressivi = [str(int(val.strip())) for val in progressivi.split(",") if val.strip()]
    query_bulk = QUERY_BULK.format(progressivi=",".join(valori_progressivi))
    cursor.execute(query_bulk, rataEmissione=rata_emissione)
    rows = cursor.fetchall()
    print(f"  Righe restituite dalla query: {len(rows)}")
    # chiave: (iscrizione, emissione, rata) → valore: (IMPONCORR, IRPEFCORR, IMPONACC, IRPEFACC)
    mappa = {(str(row[0]).strip().zfill(8), str(row[1]).strip().zfill(2), str(row[2]).strip()): row[3:] for row in rows}
    for i, (k, v) in enumerate(mappa.items()):
        if i >= 5:
            break
        print(f"  [{i+1}] chiave={k} valore={v}")
    return mappa


def flush_gruppo(fout, mappa, iscrizione, progr, rata, aggiunti):
    """Scrive il record 75 per il gruppo corrente se presente in mappa."""
    if iscrizione is None:
        return aggiunti
    chiave = (iscrizione, progr, rata)
    print(f"  [CERCA] chiave={chiave}")
    row = mappa.get(chiave)
    if row is not None:
        rec75 = build_record75(iscrizione, rata, progr, row)
        fout.write(rec75 + "\n")
        aggiunti += 1
        print(f"  [OK] Iscrizione {iscrizione}: record 75 aggiunto (progr={progr}, rata={rata})")
    else:
        print(f"  [--] Iscrizione {iscrizione}: nessun dato, record 75 saltato")
    return aggiunti


def process_file(mappa: dict, input_path: str, output_path: str) -> None:
    iscrizione_corrente = None
    progr_corrente      = None
    rata_corrente       = None
    aggiunti            = 0

    with open(input_path, "r", encoding="latin-1") as fin, \
         open(output_path, "w", encoding="latin-1", newline="\n") as fout:

        for raw_line in fin:
            # Rimuove solo il newline finale, preserva tutto il resto
            line = raw_line.rstrip("\r\n")
            record_type = line[0:2]

            if record_type == "01":
                # Fine del gruppo precedente: inserisci record 75
                aggiunti = flush_gruppo(fout, mappa, iscrizione_corrente, progr_corrente, rata_corrente, aggiunti)
                iscrizione_corrente = line[2:10].strip()
                progr_corrente      = line[16:18].strip().zfill(2)
                rata_corrente       = line[42:48].strip()

            fout.write(line + "\n")

        # Fine file: inserisci record 75 per l'ultimo gruppo
        aggiunti = flush_gruppo(fout, mappa, iscrizione_corrente, progr_corrente, rata_corrente, aggiunti)

    print(f"  Record 75 aggiunti: {aggiunti}")


def main():
    if len(sys.argv) != 5 or sys.argv[1] != "-r" or sys.argv[3] != "-p":
        print(f"Uso: python {sys.argv[0]} -r <rataEmissione> -p <valori emissione separati da virgola>  (es. -r 202603 -p 00,34,55,76)")
        sys.exit(1)
    rata_emissione = sys.argv[2]
    progressivi = sys.argv[4]

    work_dir = os.getenv("WORK_DIR")
    backup_dir = os.getenv("BACKUP_DIR")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_dsn = os.getenv("DB_DSN")
    os.makedirs(backup_dir, exist_ok=True)

    files = [f for f in os.listdir(work_dir) if os.path.isfile(os.path.join(work_dir, f))]
    if not files:
        print(f"Nessun file trovato in: {work_dir}")
        return

    print(f"Connessione a Oracle: {db_dsn}")
    connection = oracledb.connect(
        user=db_user,
        password=db_password,
        dsn=db_dsn,
    )
    try:
        with connection.cursor() as cursor:
            print(f"Caricamento mappa Oracle (rataEmissione={rata_emissione})...")
            mappa = load_mappa(cursor, rata_emissione, progressivi)
            print(f"{len(mappa)} iscrizioni caricate in mappa\n")

            for filename in sorted(files):
                input_path  = os.path.join(work_dir, filename)
                backup_path = os.path.join(backup_dir, filename)
                shutil.copy2(input_path, backup_path)
                print(f"Elaborazione: {backup_path} → {input_path}")
                process_file(mappa, backup_path, input_path)
        print("\nCompletato.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
