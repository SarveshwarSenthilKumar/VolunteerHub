import React, { useEffect, useState } from 'react';
import { Box, Typography, CircularProgress, Alert, Paper } from '@mui/material';
import api from '../api';

function Profile() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/profile/')
      .then(res => {
        setProfile(res.data.profile || {});
        setLoading(false);
      })
      .catch(err => {
        setError(err.response?.data?.message || 'Failed to load profile.');
        setLoading(false);
      });
  }, []);

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        Profile
      </Typography>
      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      {profile && (
        <Paper sx={{ p: 3, mt: 2 }}>
          <Typography variant="h6">Name: {profile.name || 'N/A'}</Typography>
          <Typography>Email: {profile.email || 'N/A'}</Typography>
        </Paper>
      )}
    </Box>
  );
}

export default Profile; 