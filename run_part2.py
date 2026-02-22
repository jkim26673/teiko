from analysis import get_connection, compute_frequencies

conn = get_connection()
freq = compute_frequencies(conn)
conn.close()

print(f"Rows: {len(freq)}")
print(freq.head(10).to_string(index=False))
