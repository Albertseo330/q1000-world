import React from "react";

export default function App() {
  return (
    <div style={{padding:"40px", fontFamily:"Arial"}}>
      <h1>Q1000.WORLD</h1>
      <p>Cognitive Responsibility OS based on generative questioning.</p>

      <h2>Q1000 Prototype v0.2</h2>

      <textarea
        placeholder="Enter a story, issue, or situation..."
        style={{
          width:"100%",
          height:"160px",
          padding:"12px",
          marginTop:"10px"
        }}
      />

      <div style={{marginTop:"30px"}}>
        <h3>Question Layers</h3>
        <ul>
          <li>What happened?</li>
          <li>Who is affected?</li>
          <li>What values collide?</li>
          <li>What information is missing?</li>
          <li>What choices are possible?</li>
          <li>Who bears responsibility?</li>
          <li>What answer can you defend?</li>
        </ul>
      </div>

      <div style={{marginTop:"30px"}}>
        <button style={{
          padding:"12px 18px",
          background:"#111",
          color:"white",
          border:"none",
          borderRadius:"8px"
        }}>
          Generate Adaptive Questions
        </button>
      </div>
    </div>
  );
}
