from dotenv import load_dotenv
import os
load_dotenv(override=True)
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

try:
    r = sb.table('señales_trading').select('*').limit(3).execute()
    print('señales_trading OK:', len(r.data), 'registros')
    if r.data:
        print('Columnas:', list(r.data[0].keys()))
except Exception as e:
    print('Error señales_trading:', e)

try:
    r2 = sb.table('blacklist').select('*').limit(3).execute()
    print('blacklist OK:', len(r2.data), 'registros')
except Exception as e:
    print('Error blacklist:', e)