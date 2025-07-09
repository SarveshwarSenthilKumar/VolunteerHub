import React, { useState } from 'react';
import { Box, Typography, TextField, Button, Paper, Alert } from '@mui/material';
import api from '../api';

function ResumeMatch() {
  const [resume, setResume] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setResult('');
    setLoading(true);
    try {
      const res = await api.post('/profile/resume-match', { resume });
      setResult(res.data.match || 'No match result.');
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to match resume.');
    }
    setLoading(false);
  };

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h3" gutterBottom>
        Resume Match
      </Typography>
      <Paper sx={{ p: 3, mt: 2 }}>
        <form onSubmit={handleSubmit}>
          <TextField
            label="Paste your resume here"
            fullWidth
            margin="normal"
            multiline
            minRows={4}
            value={resume}
            onChange={e => setResume(e.target.value)}
            required
          />
          <Button type="submit" variant="contained" color="primary" disabled={loading} sx={{ mt: 2 }}>
            Match Resume
          </Button>
        </form>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {result && <Alert severity="success" sx={{ mt: 2 }}>{result}</Alert>}
      </Paper>
    </Box>
  );
}

export default ResumeMatch; 