from analysis import get_connection, melanoma_baseline_subset

conn = get_connection()
by_project, by_response, by_sex, avg_b = melanoma_baseline_subset(conn)
conn.close()

print("Samples per project:")
print(by_project.to_string(index=False))
print()
print("Subjects by response:")
print(by_response.to_string(index=False))
print()
print("Subjects by sex:")
print(by_sex.to_string(index=False))
print()
print(f"Avg B cells (melanoma male responders, baseline): {avg_b:.2f}")
