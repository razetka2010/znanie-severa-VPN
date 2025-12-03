import sqlite3

# Подключаемся к базе данных
conn = sqlite3.connect('keys.db')
cursor = conn.cursor()

print("📋 Текущие платежи:")
cursor.execute("SELECT id, status, admin_key FROM payments ORDER BY id")
payments = cursor.fetchall()

for payment in payments:
    print(f"ID: {payment[0]}, Статус: {payment[1]}, Ключ: {payment[2]}")

print("\n🗑️ Удаление платежей...")

# Удаляем платежи с ID 1, 2, 3, 4
payment_ids_to_delete = [1, 2, 3, 4]

for payment_id in payment_ids_to_delete:
    cursor.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    print(f"✅ Платеж ID {payment_id} удален")

# Проверяем что осталось
print("\n📋 Оставшиеся платежи:")
cursor.execute("SELECT id, status, admin_key FROM payments ORDER BY id")
remaining = cursor.fetchall()

for payment in remaining:
    print(f"ID: {payment[0]}, Статус: {payment[1]}, Ключ: {payment[2]}")

conn.commit()
conn.close()

print(f"\n🎯 Удалено платежей: {len(payment_ids_to_delete)}")
print("✅ Готово!")