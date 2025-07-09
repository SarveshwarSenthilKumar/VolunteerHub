import React, { useState, useEffect } from 'react';
import { Box, Typography, Button, Container } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

function Home() {
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    // Check for admin cookie
    const checkAdminStatus = () => {
      const cookies = document.cookie.split(';');
      const adminCookie = cookies.find(cookie => cookie.trim().startsWith('is_admin='));
      if (adminCookie) {
        const adminValue = adminCookie.split('=')[1];
        setIsAdmin(adminValue === 'true');
      }
    };

    checkAdminStatus();
  }, []);

  return (
    <Box sx={{ py: 10, background: 'linear-gradient(135deg, #1976d2 0%, #ff4081 100%)', color: '#fff', minHeight: '80vh' }}>
      <Container maxWidth="md" sx={{ textAlign: 'center' }}>
        <Typography variant="h1" gutterBottom>
          VolunteerHub
        </Typography>
        <Typography variant="h5" sx={{ mb: 4 }}>
          Discover, match, and make a difference. The next generation platform for volunteers and organizations.
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Button
            variant="contained"
            color="secondary"
            size="large"
            component={RouterLink}
            to="/opportunities"
            sx={{ fontWeight: 700, px: 4, py: 1.5, fontSize: '1.2rem', borderRadius: 3 }}
          >
            Find Opportunities
          </Button>
          {isAdmin && (
            <Button
              variant="outlined"
              color="inherit"
              size="large"
              component={RouterLink}
              to="/admin"
              sx={{ 
                fontWeight: 700, 
                px: 4, 
                py: 1.5, 
                fontSize: '1.2rem', 
                borderRadius: 3,
                borderColor: '#fff',
                color: '#fff',
                '&:hover': {
                  borderColor: '#fff',
                  backgroundColor: 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              Admin Dashboard
            </Button>
          )}
        </Box>
      </Container>
    </Box>
  );
}

export default Home; 