const express = require('express');
const router = express.Router();
const { getAIMove } = require('../controllers/aiController');

router.post('/move', getAIMove);

module.exports = router;