# Connecting Frontend to Backend

## Quick Setup

Your frontend (`index.html`) is now configured to connect to your backend API at:
**https://backend-bp-2041.onrender.com**

## What's Configured

✅ **Default API URL**: Set to `https://backend-bp-2041.onrender.com`
✅ **API URL Saving**: Automatically saved to browser localStorage
✅ **Fallback**: If API URL is empty, uses your backend URL

## How It Works

1. **Frontend** (`index.html`) sends requests to your backend API
2. **Backend** (`app.py`) processes calculations and saves to database
3. **Results** are returned to frontend and displayed

## API Endpoints Used

- `POST /calculate_batch` - Calculate costs for multiple links
- All calculations are automatically saved to database

## Testing the Connection

1. Open your `index.html` file in a browser (or deploy to GitHub Pages)
2. Enter an address and ZIP code
3. Paste a Buyee link
4. Click "Calculate All"
5. Check browser console (F12) for any errors

## Troubleshooting

### CORS Errors
- Make sure your backend has CORS enabled (already done in `app.py`)
- Check backend is running at `https://backend-bp-2041.onrender.com`

### Connection Failed
- Verify backend URL is correct
- Check Render dashboard - backend should be "Live"
- Test backend directly: Visit `https://backend-bp-2041.onrender.com` (should show Flask error page - this is OK!)

### Database Not Saving
- Check Render logs for database errors
- Verify `DATABASE_URL` is set (or SQLite will be used automatically)

## Updating the API URL

The API URL is saved in browser localStorage. To change it:
1. Edit the input field in the UI
2. It will be saved automatically
3. Or clear browser localStorage to reset

## Deployment

### Frontend (GitHub Pages)
1. Push `index.html` to: https://github.com/m3owle0/buyee-landed-price
2. Enable GitHub Pages in repo settings
3. Your site will be live at: `https://m3owle0.github.io/buyee-landed-price/`

### Backend (Render)
- Already deployed at: https://backend-bp-2041.onrender.com
- Auto-deploys when you push to: https://github.com/m3owle0/backend-bp

## Next Steps

1. **Deploy frontend** to GitHub Pages (if not already done)
2. **Test the connection** - try calculating a cost
3. **Check database** - visit `/api/stats` to see saved calculations
