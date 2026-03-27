interface ImagePanelProps {
  imageUrl: string | null;
}

export function ImagePanel({ imageUrl }: ImagePanelProps) {
  return (
    <div
      style={{
        flex: 1,
        borderRight: "1px solid #ccc",
        overflow: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#fafafa",
      }}
    >
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="LTspice schematic"
          style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
        />
      ) : (
        <span style={{ color: "#999" }}>Upload an LTspice screenshot</span>
      )}
    </div>
  );
}
