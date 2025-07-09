import React, { useEffect, useState } from 'react';
import { Box, Typography, CircularProgress, Alert, Card, CardContent, Grid } from '@mui/material';
import api from '../api';

function Saved() {
  const [saved, setSaved] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/opportunities/saved')
      .then(res => {
        setSaved(res.data.saved || []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.response?.data?.message || 'Failed to load saved opportunities.');
        setLoading(false);
      });
  }, []);

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        Saved Opportunities
      </Typography>
      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      <Grid container spacing={2}>
        {saved.map((opp, idx) => (
          <Grid item xs={12} md={6} lg={4} key={idx}>
            <Card>
              <CardContent>
                <Typography variant="h5">{opp.title || 'Untitled'}</Typography>
                <Typography>{opp.description || 'No description.'}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

export default Saved; 