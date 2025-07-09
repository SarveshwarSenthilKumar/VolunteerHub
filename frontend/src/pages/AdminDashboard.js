import React, { useEffect, useState } from 'react';
import { Box, Typography, CircularProgress, Alert, Paper } from '@mui/material';
import api from '../api';

function AdminDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/admin/dashboard')
      .then(res => {
        setDashboard(res.data.dashboard || {});
        setLoading(false);
      })
      .catch(err => {
        setError(err.response?.data?.message || 'Failed to load dashboard.');
        setLoading(false);
      });
  }, []);

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        Admin Dashboard
      </Typography>
      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      {dashboard && (
        <Paper sx={{ p: 3, mt: 2 }}>
          <Typography variant="h6">Welcome, Admin!</Typography>
          <Typography>Total Users: {dashboard.total_users || 0}</Typography>
          <Typography>Total Opportunities: {dashboard.total_opportunities || 0}</Typography>
        </Paper>
      )}
    </Box>
  );
}

export default AdminDashboard; 