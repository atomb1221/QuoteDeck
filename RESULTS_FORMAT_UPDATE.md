# Results Format Update

## Changes Made

### ✅ Simplified Results Display

**Old Format (Verbose):**
```
STEEL PRICING QUOTE
================================================================================

Product: 25 x 25 x 3 mm (Code: 2)
  Weight: 1.11 kg/m
  Length: 6.3 m
  Tonnage: £850.00/ton
  Price per metre: £0.94
  Total: £5.94

Product: 80 x 80 x 6 mm (Code: 18)
  Weight: 7.25 kg/m
  Length: 6.3 m
  Tonnage: £850.00/ton
  Price per metre: £6.16
  Total: £38.82
...
```

**New Format (Clean & Simple):**
```
25 x 25 x 3 mm = £0.94p/l
80 x 80 x 6 mm = £6.16p/l
25 x 10 mm = £1.70p/l
100 x 100 x 6 mm = £5.10p/l

Subtotal: £83.48
VAT (20%): £16.70
Total: £100.18
```

### Key Improvements

1. **Cleaner Format**
   - One line per product
   - Shows product description and price per length only
   - Format: `Product Description = £X.XXp/l`

2. **Results Displayed in App**
   - Results appear in the "💷 Pricing Results" section
   - Larger font (11pt Courier New)
   - Light grey background (#f8f9fa) for better readability
   - Increased height (12 lines)

3. **Summary at Bottom**
   - Subtotal (total of all lengths × price/length)
   - VAT at 20%
   - Final total including VAT

## Example

### Input:
```
Email: 3no 25x25x3mm angle, 5no 80x80x6 angle
Default Length: 6.3m
Default Tonnage: £850/ton
```

### Output in App:
```
25 x 25 x 3 mm = £0.94p/l
80 x 80 x 6 mm = £6.16p/l

Subtotal: £44.76
VAT (20%): £8.95
Total: £53.71
```

## What "p/l" Means

- **p/l** = Price per length (per metre)
- This is the standard pricing format for steel products
- Calculated as: (weight × tonnage) / 1000

## Benefits

✅ **Much cleaner** - No clutter, just the essentials
✅ **Easy to read** - One line per product
✅ **Professional** - Industry-standard format
✅ **In-app display** - See results immediately without copying
✅ **Copy-ready** - Still can copy to clipboard for emails

## Usage

1. Extract items from email
2. Enter or apply lengths and tonnage
3. Click "💰 Calculate Prices" (Green button)
4. Results appear in the "💷 Pricing Results" section
5. Click "📄 Copy to Clipboard" (Orange button) to copy if needed

The results are now much cleaner and easier to read!
