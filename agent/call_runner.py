import os
import csv
import sys
import argparse
import asyncio
from dotenv import load_dotenv

# Ensure we can import from agent/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import make_call

# Load environment variables
load_dotenv()

async def run_batch(limit: int = None, dry_run: bool = False):
    # Locate businesses.csv
    # It will be in the project root directory
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(root_dir, "businesses.csv")
    
    # Fallback to businesses.example.csv if businesses.csv does not exist yet
    if not os.path.exists(csv_path):
        csv_path = os.path.join(root_dir, "businesses.example.csv")
        print(f"businesses.csv not found. Falling back to example CSV: {csv_path}")
        
    if not os.path.exists(csv_path):
        print(f"Error: No CSV file found at {csv_path} or businesses.example.csv")
        return
        
    print(f"Reading businesses from {csv_path}...")
    businesses = []
    
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Normalize column names by lowercasing and stripping spaces
            fieldnames = [fn.strip().lower() for fn in reader.fieldnames]
            
            # Map normalized field names to original
            col_map = {}
            for original in reader.fieldnames:
                normalized = original.strip().lower()
                if 'name' in normalized:
                    col_map['name'] = original
                elif 'phone' in normalized:
                    col_map['phone'] = original
                elif 'type' in normalized:
                    col_map['type'] = original
            
            if 'name' not in col_map or 'phone' not in col_map or 'type' not in col_map:
                print("Error: CSV must contain 'name', 'phone', and 'type' columns.")
                print(f"Found headers: {reader.fieldnames}")
                return
                
            for row in reader:
                businesses.append({
                    "name": row[col_map['name']].strip(),
                    "phone": row[col_map['phone']].strip(),
                    "type": row[col_map['type']].strip()
                })
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    if not businesses:
        print("No businesses found in CSV.")
        return

    # Apply limit if specified
    if limit is not None and limit > 0:
        businesses = businesses[:limit]
        print(f"Limit applied: only processing the first {limit} record(s).")
        
    print(f"Total businesses to dial: {len(businesses)}")
    
    for i, biz in enumerate(businesses, start=1):
        name = biz["name"]
        phone = biz["phone"]
        b_type = biz["type"]
        
        print(f"[{i}/{len(businesses)}] Calling {name} at {phone} ({b_type})...")
        
        if dry_run:
            print(f"  [DRY-RUN] Would call {name} at {phone} ({b_type})")
            # In dry-run mode, we still post a dry-run log to backend so the UI updates and shows it
            # But let's pass dry_run=True to make_call which does simulation
            outcome = await make_call(name, phone, b_type, dry_run=True)
            print(f"  [DRY-RUN] done. Simulated Outcome: {outcome}")
        else:
            try:
                outcome = await make_call(name, phone, b_type, dry_run=False)
                print(f"  done. Outcome: {outcome}")
            except Exception as e:
                print(f"  Error placing call: {e}")
                
        # Wait a small delay between calls
        await asyncio.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="SmartReception batch dialer")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of businesses to call")
    parser.add_argument("--dry-run", action="store_true", help="Print/simulate call actions without active dialing")
    args = parser.parse_args()
    
    asyncio.run(run_batch(limit=args.limit, dry_run=args.dry_run))

if __name__ == "__main__":
    main()
