"""
Script CLI para identificar e processar follow-ups de leads.

Uso:
    python scripts/run_followups.py [--dry-run] [--limit N]
"""

import os
import sys
import argparse

# Add app to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "app"))

from agent.followup import find_leads_for_followup, save_followup_sent


def main():
    parser = argparse.ArgumentParser(description="Processa follow-ups de leads")
    parser.add_argument("--dry-run", action="store_true", help="Apenas lista, não envia")
    parser.add_argument("--limit", type=int, default=10, help="Limite de leads")
    parser.add_argument("--leads-path", default="data/leads.jsonl", help="Caminho do JSONL")

    args = parser.parse_args()

    print(f"\n=== Follow-up de Leads ===")
    print(f"Dry-run: {args.dry_run}")
    print(f"Limite: {args.limit}\n")

    # Encontra candidatos
    candidates = find_leads_for_followup(args.leads_path, limit=args.limit)

    if not candidates:
        print("✓ Nenhum lead precisa de follow-up no momento.\n")
        return

    print(f"Encontrados {len(candidates)} lead(s) para follow-up:\n")

    for i, item in enumerate(candidates, 1):
        lead = item["lead"]
        followup = item["followup"]

        session_id = lead.get("session_id")
        name = lead.get("lead_profile", {}).get("name", "Lead")
        temp = lead.get("lead_score", {}).get("temperature", "?")
        grade = lead.get("quality_score", {}).get("grade", "?")

        print(f"[{i}] {session_id}")
        print(f"    Nome: {name}")
        print(f"    Temperatura: {temp} | Grade: {grade}")
        print(f"    Follow-up: {followup['followup_key']}")
        print(f"    Mensagem: \"{followup['message_text']}\"")
        print(f"    Razões: {followup['reasons']}")

        if not args.dry_run:
            # Em produção, aqui enviaria via WhatsApp/SMS
            save_followup_sent(session_id, followup['followup_key'])
            print(f"    ✓ Registrado como enviado\n")
        else:
            print(f"    [DRY-RUN] Não enviado\n")

    if args.dry_run:
        print(f"\n✓ Dry-run completo. Use sem --dry-run para registrar envios.\n")
    else:
        print(f"\n✓ {len(candidates)} follow-up(s) processados.\n")


if __name__ == "__main__":
    main()
