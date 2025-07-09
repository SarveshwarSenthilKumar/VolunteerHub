import React, { useState } from 'react';
import { Box, Typography, TextField, Button, Paper, Container, Alert } from '@mui/material';
import api from '../api';

function Signup() {
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const res = await api.post('/auth/signup', { 
        username, 
        name, 
        email, 
        password, 
        city, 
        state, 
        phone 
      });
      if (res.data.token) {
        localStorage.setItem('token', res.data.token);
        window.location.href = '/';
      } else {
        setError('Invalid response from server.');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Signup failed.');
    }
  };

  return (
    <Container maxWidth="xs" sx={{ mt: 8 }}>
      <Paper elevation={3} sx={{ p: 4 }}>
        <Typography variant="h4" gutterBottom align="center">
          Sign Up
        </Typography>
        {error && <Alert severity="error">{error}</Alert>}
        <Box component="form" onSubmit={handleSubmit}>
          <TextField
            label="Username"
            fullWidth
            margin="normal"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <TextField
            label="Full Name"
            fullWidth
            margin="normal"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <TextField
            label="Email"
            type="email"
            fullWidth
            margin="normal"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <TextField
            label="Password"
            type="password"
            fullWidth
            margin="normal"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <TextField
            label="City"
            fullWidth
            margin="normal"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            required
          />
          <TextField
            label="State"
            fullWidth
            margin="normal"
            value={state}
            onChange={(e) => setState(e.target.value)}
            required
          />
          <TextField
            label="Phone Number"
            fullWidth
            margin="normal"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            sx={{ mt: 2, fontWeight: 700 }}
          >
            Sign Up
          </Button>
        </Box>
      </Paper>
    </Container>
  );
}

export default Signup; 