import React, { useEffect, useState } from 'react';
import { Box, Typography, CircularProgress, Alert, Card, CardContent, Button, Grid } from '@mui/material';
import api from '../api';

function Opportunities() {
  const [opps, setOpps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/opportunities/')
      .then(res => {
        setOpps(res.data.opportunities || []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.response?.data?.message || 'Failed to load opportunities.');
        setLoading(false);
      });
  }, []);

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        Opportunities
      </Typography>
      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      <Grid container spacing={2}>
        {opps.map((opp, idx) => (
          <Grid item xs={12} md={6} lg={4} key={idx}>
            <Card>
              <CardContent>
                <Typography variant="h5">{opp.title || 'Untitled'}</Typography>
                <Typography>{opp.description || 'No description.'}</Typography>
                <Button variant="contained" color="primary" sx={{ mt: 2 }}>
                  Save
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

export default Opportunities; 