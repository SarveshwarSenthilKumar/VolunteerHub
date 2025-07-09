import React from 'react';
import { Box, Typography, Button, Container } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

function Home() {
  return (
    <Box sx={{ py: 10, background: 'linear-gradient(135deg, #1976d2 0%, #ff4081 100%)', color: '#fff', minHeight: '80vh' }}>
      <Container maxWidth="md" sx={{ textAlign: 'center' }}>
        <Typography variant="h1" gutterBottom>
          VolunteerHub
        </Typography>
        <Typography variant="h5" sx={{ mb: 4 }}>
          Discover, match, and make a difference. The next generation platform for volunteers and organizations.
        </Typography>
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
      </Container>
    </Box>
  );
}

export default Home; 