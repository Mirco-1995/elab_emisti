import os

# Connessione Oracle
DB_USER     = os.getenv("DB_USER", "sptowner")
DB_PASSWORD = os.getenv("DB_PASSWORD", "svilsnpc10$")
DB_DSN      = os.getenv("DB_DSN", "c1v-orc-snpc10.coll.tesoro.it:1521/SPTES.TESORO.IT")  # es. "myhost:1521/MYSERVICE" oppure TNS alias

WORK_DIR   = os.getenv("WORK_DIR",   "/home6/pemco/202604/ordinaria/elaborazioni/files/mese/emi132/")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/home6/pemco/202604/ordinaria/elaborazioni/files/mese/emi132/backup")
