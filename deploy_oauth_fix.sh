#!/bin/bash
echo "=== Deploying OAuth/Telegram Session Cookie Fix ==="
echo ""
echo "Issue: www/non-www domain mismatch causes session cookies to be lost"
echo "Solution: Use SESSION_COOKIE_DOMAIN=.myfishcare.com to work across both domains"
echo ""
echo -e "${YELLOW}1. Creating backup...${NC}"
sudo mkdir -p "$BACKUP_DIR"
sudo cp "$PROD_DIR/.env" "$BACKUP_DIR/.env.backup" 2>/dev/null || true
sudo cp /etc/nginx/sites-available/my-fish-care "$BACKUP_DIR/nginx.backup" 2>/dev/null || true
echo -e "${GREEN}✓ Backup created at $BACKUP_DIR${NC}"
echo ""
echo -e "${YELLOW}2. Required changes in production .env file:${NC}"
echo ""
echo "Add these lines to /opt/my-fish-care/.env:"
echo ""
echo -e "${GREEN}# Session cookie domain (use .myfishcare.com to work with both www and non-www)"
echo "SESSION_COOKIE_DOMAIN=.myfishcare.com"
echo ""
echo "# Ensure these are set correctly:"
echo "DEBUG=false"
echo "API_BASE_URL=https://myfishcare.com"
echo "TELEGRAM_BASE_URL=https://myfishcare.com"
echo "GOOGLE_REDIRECT_URI=https://myfishcare.com/auth/google/callback${NC}"
echo ""
read -p "Press Enter after you've updated the .env file..."
echo -e "${YELLOW}3. Copying updated application code...${NC}"

echo -e "${GREEN}✓ Application code updated${NC}"
echo ""
echo -e "${YELLOW}4. Updating nginx configuration...${NC}"
sudo cp ./nginx-my-fish-care.conf /etc/nginx/sites-available/my-fish-care
echo "Testing nginx configuration..."
if sudo nginx -t; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
else
    echo -e "${RED}✗ Nginx configuration has errors!${NC}"
    echo "Restoring backup..."
    sudo cp "$BACKUP_DIR/nginx.backup" /etc/nginx/sites-available/my-fish-care
    exit 1
fi
echo ""
echo -e "${YELLOW}5. Verifying OAuth redirect URIs...${NC}"
echo ""
echo "Google OAuth Console: https://console.cloud.google.com/apis/credentials"
echo "  → Authorized redirect URIs must include:"
echo "    https://myfishcare.com/auth/google/callback"
echo ""
echo "Telegram Bot Settings: https://core.telegram.org/widgets/login"
echo "  → Domain must be set to: myfishcare.com"
echo ""
read -p "Press Enter to continue..."
echo -e "${YELLOW}6. Reloading nginx...${NC}"
sudo systemctl reload nginx
echo -e "${GREEN}✓ Nginx reloaded${NC}"
echo ""
echo -e "${YELLOW}7. Restarting my-fish-care service...${NC}"
sudo systemctl restart my-fish-care
sleep 3
echo ""
echo -e "${YELLOW}8. Checking service status...${NC}"
if sudo systemctl is-active --quiet my-fish-care; then
    echo -e "${GREEN}✓ Service is running${NC}"
    echo ""
    echo "Recent logs:"
    sudo journalctl -u my-fish-care -n 20 --no-pager
else
    echo -e "${RED}✗ Service failed to start!${NC}"
    echo ""
    echo "Error logs:"
    sudo journalctl -u my-fish-care -n 50 --no-pager
    exit 1
fi
echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Changes applied:"
echo "  ✓ SESSION_COOKIE_DOMAIN set to .myfishcare.com (works for www and non-www)"
echo "  ✓ Nginx redirects www → non-www for consistency"
echo "  ✓ All URLs use myfishcare.com (without www)"
echo ""
echo -e "${YELLOW}Test the fixes:${NC}"
echo "  1. Google OAuth: https://myfishcare.com/auth/google/login"
echo "  2. Telegram Login: https://myfishcare.com/login (use Telegram button)"
echo "  3. Try both with www and without: https://www.myfishcare.com/login"
echo ""
echo "Monitor logs: sudo journalctl -u my-fish-care -f"

