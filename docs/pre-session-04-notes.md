## Contrato tipado con Pydantic

Nuevo schemas.py con:
- Enums projectType, DetailLevel, OutputFormat
- EstimationRequest_ description, project_type, detail_level, output_format
- EstimationResponse: text, prompt_version

## Endpoint actualizado

El /estimate importa EstimationRequest y usa request.description como entrada para generate_estimation(). De momento el resto de campos de EstimationRequest no se usan en el prompt.

## Formulario de cliente

Sustituido el chat por st.form:
- st.text_area para la descripción.
- tres st-selectbox reusando los tipos de app.schemas

Al enviar se construye un EstimationRequest real. Validación Pydantic en el cliente, antes de la llamada de red y se hace POST con este JSON.