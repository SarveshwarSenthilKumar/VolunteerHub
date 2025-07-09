import React, { useState } from 'react';
import { Box, Typography, TextField, Button, Paper, Alert } from '@mui/material';
import api from '../api';

function AIEmail() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setResult('');
    setLoading(true);
    try {
      const res = await api.post('/ai/generate-email', { input });
      setResult(res.data.email || 'No email generated.');
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to generate email.');
    }
    setLoading(false);
  };

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        AI Email
      </Typography>
      <Paper sx={{ p: 3, mt: 2 }}>
        <form onSubmit={handleSubmit}>
          <TextField
            label="Describe your request"
            fullWidth
            margin="normal"
            value={input}
            onChange={e => setInput(e.target.value)}
            required
          />
          <Button type="submit" variant="contained" color="primary" disabled={loading} sx={{ mt: 2 }}>
            Generate Email
          </Button>
        </form>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {result && <Alert severity="success" sx={{ mt: 2 }}>{result}</Alert>}
      </Paper>
    </Box>
  );
}

export default AIEmail; 