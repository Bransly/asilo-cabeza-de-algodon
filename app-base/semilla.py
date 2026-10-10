"""
CARGA INICIAL DE DATOS

Deja el sistema utilizable desde el primer arranque: las especialidades,
medicos y enfermeros que aporta la fundacion, y tres internos de ejemplo con
su ficha medica. Solo se ejecuta si la base de datos esta vacia.
"""
import os
import secrets
from datetime import date

from sqlalchemy import func, select

from auth import cifrar_contrasena
from database import Sesion
from models import (
    Enfermero, Especialidad, FichaMedica, Medico, MedicamentoPermanente,
    Paciente, RolUsuario, Usuario,
)

ESPECIALIDADES = [
    ("Cardiologia", [("Dr. Luis Herrera", "12345")]),
    ("Neurologia", [("Dra. Ana Morales", "23456")]),
    ("Traumatologia", [("Dr. Pedro Castillo", "34567")]),
    ("Geriatria", [("Dra. Silvia Mendez", "45678"), ("Dr. Mario Arriaga", "56789")]),
]

ENFERMEROS = [
    ("Enf. Marta Lopez", "Matutino"),
    ("Enf. Jose Ramirez", "Vespertino"),
    ("Enf. Claudia Similox", "Matutino"),
]

# Usuario de cada rol de la matriz de permisos. Las personas son ficticias.
# Las contrasenas NO estan en el codigo: se leen de las variables de entorno
# CLAVE_INICIAL_ADMIN y CLAVE_INICIAL_USUARIOS (archivo .env, fuera del
# repositorio). Si no se definen, se genera una clave aleatoria y se muestra
# una sola vez en el registro del contenedor. En ambos casos la clave es
# temporal: el sistema obliga a cambiarla en el primer ingreso.
USUARIOS = [
    ("Brandon Madrid", "admin", RolUsuario.ADMINISTRADOR),
    ("Dr. Carlos Say", "mgeneral", RolUsuario.MEDICO_GENERAL),
    ("Dr. Luis Herrera", "especialista", RolUsuario.MEDICO_ESPECIALISTA),
    ("Enf. Marta Lopez", "enfermeria", RolUsuario.ENFERMERIA),
    ("Lic. Ana Chavez", "laboratorio", RolUsuario.LABORATORIO),
    ("Lic. Oscar Tuy", "farmacia", RolUsuario.FARMACIA),
    ("Sra. Elsa Coy", "caja", RolUsuario.CAJA),
    ("Fundacion Vida Digna", "fundacion", RolUsuario.FUNDACION),
]


def _clave_inicial(variable: str) -> str:
    clave = os.getenv(variable, "").strip()
    if clave:
        return clave
    clave = secrets.token_urlsafe(12)
    print(f"[semilla] {variable} no esta definida. Clave temporal generada: {clave}")
    return clave

PACIENTES = [
    {
        "nombre": "Rosa Elvira Perez", "edad": 82,
        "fecha_ingreso": date(2023, 3, 14),
        "motivo_ingreso": "Familiares no pueden brindarle atencion permanente.",
        "familiar_nombre": "Carmen Perez",
        "correo_familiar": "carmen.perez@ejemplo.com",
        "telefono_familiar": "5512-3344", "cuota_mensual": 900.0,
        "psicopatologia": "Deterioro cognitivo leve.",
        "padecimientos": "Hipertension arterial. Artrosis de rodilla.",
        "alergias": "Penicilina.",
        "medicamentos": [("Losartan 50mg", "1 tableta", "Cada 24 horas"),
                         ("Calcio + vitamina D", "1 tableta", "Cada 24 horas")],
    },
    {
        "nombre": "Julio Cesar Ramirez", "edad": 78,
        "fecha_ingreso": date(2024, 1, 8),
        "motivo_ingreso": "Ingreso voluntario tras fallecimiento de su conyuge.",
        "familiar_nombre": "Mario Ramirez",
        "correo_familiar": "mario.ramirez@ejemplo.com",
        "telefono_familiar": "4478-9021", "cuota_mensual": 850.0,
        "psicopatologia": "Cuadro depresivo en seguimiento.",
        "padecimientos": "Diabetes mellitus tipo 2.",
        "alergias": "Ninguna conocida.",
        "medicamentos": [("Metformina 850mg", "1 tableta", "Cada 12 horas")],
    },
    {
        "nombre": "Amparo Gonzalez Lopez", "edad": 90,
        "fecha_ingreso": date(2022, 9, 30),
        "motivo_ingreso": "Referida por trabajo social municipal.",
        "familiar_nombre": "Lucia Gonzalez",
        "correo_familiar": "lucia.gonzalez@ejemplo.com",
        "telefono_familiar": "3390-1157", "cuota_mensual": 750.0,
        "psicopatologia": "Demencia senil, etapa inicial.",
        "padecimientos": "Osteoporosis. Cataratas en ojo derecho.",
        "alergias": "Sulfas.",
        "medicamentos": [("Alendronato 70mg", "1 tableta", "Semanal")],
    },
]


def cargar_datos_iniciales() -> None:
    sesion = Sesion()
    try:
        if sesion.scalar(select(func.count()).select_from(Usuario)):
            return  # ya hay datos: no se duplica nada

        for nombre_especialidad, medicos in ESPECIALIDADES:
            especialidad = Especialidad(nombre=nombre_especialidad)
            sesion.add(especialidad)
            sesion.flush()
            for nombre_medico, colegiado in medicos:
                sesion.add(Medico(nombre=nombre_medico, colegiado=colegiado,
                                  especialidad_id=especialidad.id))

        for nombre, turno in ENFERMEROS:
            sesion.add(Enfermero(nombre=nombre, turno=turno))

        clave_admin = _clave_inicial("CLAVE_INICIAL_ADMIN")
        clave_usuarios = _clave_inicial("CLAVE_INICIAL_USUARIOS")
        for nombre, cuenta, rol in USUARIOS:
            clave = clave_admin if rol == RolUsuario.ADMINISTRADOR else clave_usuarios
            sesion.add(Usuario(nombre=nombre, usuario=cuenta, rol=rol,
                               hash_contrasena=cifrar_contrasena(clave),
                               debe_cambiar_contrasena=True))

        for datos in PACIENTES:
            paciente = Paciente(
                nombre=datos["nombre"], edad=datos["edad"],
                fecha_ingreso=datos["fecha_ingreso"],
                motivo_ingreso=datos["motivo_ingreso"],
                familiar_nombre=datos["familiar_nombre"],
                correo_familiar=datos["correo_familiar"],
                telefono_familiar=datos["telefono_familiar"],
                cuota_mensual=datos["cuota_mensual"],
            )
            paciente.ficha = FichaMedica(
                psicopatologia=datos["psicopatologia"],
                padecimientos=datos["padecimientos"],
                alergias=datos["alergias"],
            )
            for nombre_med, dosis, frecuencia in datos["medicamentos"]:
                paciente.medicamentos_permanentes.append(
                    MedicamentoPermanente(nombre=nombre_med, dosis=dosis,
                                          frecuencia=frecuencia))
            sesion.add(paciente)

        sesion.commit()
        print("[semilla] usuarios, catalogos y pacientes de ejemplo cargados")
    finally:
        sesion.close()
