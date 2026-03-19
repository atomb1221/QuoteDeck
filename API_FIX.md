# API Model Fix

## Issue
The application was using `claude-3-5-sonnet-20241022` which returned a 404 error because:
- This model is not available with your API key tier
- The model identifier may not exist or requires a different subscription level

## Solution
Updated the application to use **Claude 3 Haiku** (`claude-3-haiku-20240307`) which:
- ✅ Works with your API key
- ✅ Is fast and efficient for extraction tasks
- ✅ Provides accurate JSON responses
- ✅ More cost-effective

## Changes Made
Updated both AI extraction methods in [steel_pricer.py](steel_pricer.py):
1. `extract_items_from_email()` - Line 111
2. `extract_quick_quote()` - Line 158

Changed from:
```python
model="claude-3-5-sonnet-20241022"
```

To:
```python
model="claude-3-haiku-20240307"
```

## Testing
Tested successfully with your API key - extraction works perfectly!

Example test:
```
Email: "Can I get a quote for 25x25x3 angle and 40x40x6 angle?"

Extracted:
[
  {"product": "25x25x3", "length": 0, "tonnage": 0},
  {"product": "40x40x6", "length": 0, "tonnage": 0}
]
```

## Status
✅ **FIXED** - Application is now fully functional!

You can now:
1. Paste customer emails
2. Click "🔍 Extract Items"
3. See products extracted correctly
4. Edit lengths and tonnages
5. Calculate prices

The error is resolved and the application should work smoothly now.
